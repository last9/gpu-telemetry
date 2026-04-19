#!/usr/bin/env python3
# Copyright (c) Last9, Inc.
"""CLI command for GPU fleet health monitoring — predictive failure signals."""

import itertools
import logging
import socket
from dataclasses import dataclass, field
from typing import Collection, Mapping, Optional

import click
from l9gpu.exporters import registry
from l9gpu.monitoring.click import (
    click_default_cmd,
    cluster_option,
    DynamicEpilogCommand,
    get_docs_for_references,
    get_docs_for_registry,
    once_option,
    sink_option,
    sink_opts_option,
)
from l9gpu.monitoring.clock import Clock, ClockImpl
from l9gpu.monitoring.fleet_health import FleetHealthTracker
from l9gpu.monitoring.sink.protocol import DataType, SinkAdditionalParams, SinkImpl
from l9gpu.monitoring.sink.utils import Factory
from l9gpu.schemas.log import Log
from omegaconf import OmegaConf as oc
from typeguard import typechecked

LOGGER_NAME = "fleet_health_monitor"
logger = logging.getLogger(LOGGER_NAME)


@dataclass
class CliObjectImpl:
    registry: Mapping[str, Factory[SinkImpl]] = field(default_factory=lambda: registry)
    clock: Clock = field(default_factory=ClockImpl)

    def format_epilog(self) -> str:
        return get_docs_for_registry(self.registry) + get_docs_for_references(
            [
                "https://modal.com/blog/gpu-health",
                "https://docs.nvidia.com/deploy/xid-errors/index.html",
            ]
        )

    def looptimes(self, once: bool):
        if once:
            return range(1)
        return itertools.count(0)


class CustomCommand(DynamicEpilogCommand[CliObjectImpl], obj_cls=CliObjectImpl):
    pass


_default_obj = CliObjectImpl()


@click_default_cmd(cls=CustomCommand, context_settings={"obj": _default_obj})
@cluster_option
@sink_option
@sink_opts_option
@click.option(
    "--health-window",
    type=click.IntRange(min=60),
    default=300,
    show_default=True,
    help="Sliding window in seconds for rate/trend calculations.",
)
@click.option(
    "--push-interval",
    type=click.IntRange(min=1),
    default=60,
    show_default=True,
    help="Interval in seconds between metric pushes.",
)
@once_option
@click.pass_obj
@typechecked
def main(
    obj: CliObjectImpl,
    cluster: Optional[str],
    sink: str,
    sink_opts: Collection[str],
    health_window: int,
    push_interval: int,
    once: bool,
) -> None:
    """Monitor GPU fleet health: XID rates, ECC trends, PCIe link downtraining, thermal ramp, health score."""
    try:
        import pynvml  # type: ignore

        pynvml.nvmlInit()
    except Exception as exc:
        raise click.UsageError(f"NVML not available: {exc}")

    hostname = socket.gethostname().replace(".maas", "")
    base_resource = [f"host.name={hostname}"]
    if cluster:
        base_resource.append(f"k8s.cluster.name={cluster}")

    augmented_sink_opts = list(sink_opts)
    for attr in base_resource:
        augmented_sink_opts.append(f"metric_resource_attributes.{attr}")
    try:
        sink_impl = obj.registry[sink](**oc.from_dotlist(augmented_sink_opts))
    except ValueError as e:
        raise click.UsageError(str(e))

    tracker = FleetHealthTracker(window_seconds=float(health_window))
    device_count = pynvml.nvmlDeviceGetCount()

    for _ in obj.looptimes(once):
        metrics_list = []
        for i in range(device_count):
            try:
                handle = pynvml.nvmlDeviceGetHandleByIndex(i)
                uuid = pynvml.nvmlDeviceGetUUID(handle)
                model = pynvml.nvmlDeviceGetName(handle)

                # XID — last error code (0 = none)
                # Use NVML field value query for NVML_FI_DEV_LAST_XID_ERROR
                xid = None
                try:
                    field_values = pynvml.nvmlDeviceGetFieldValues(
                        handle, [pynvml.NVML_FI_DEV_XID_ERRORS]
                    )
                    if field_values and len(field_values) > 0:
                        xid_val = (
                            field_values[0].value.sllVal
                            if hasattr(field_values[0].value, "sllVal")
                            else int(field_values[0].value)
                        )
                        if xid_val != 0:
                            xid = int(xid_val)
                except Exception:
                    pass

                # ECC
                try:
                    sbe = pynvml.nvmlDeviceGetTotalEccErrors(
                        handle,
                        pynvml.NVML_MEMORY_ERROR_TYPE_CORRECTED,
                        pynvml.NVML_VOLATILE_ECC,
                    )
                    dbe = pynvml.nvmlDeviceGetTotalEccErrors(
                        handle,
                        pynvml.NVML_MEMORY_ERROR_TYPE_UNCORRECTED,
                        pynvml.NVML_VOLATILE_ECC,
                    )
                except Exception:
                    sbe = dbe = None

                # Temperature
                try:
                    temp = float(
                        pynvml.nvmlDeviceGetTemperature(
                            handle, pynvml.NVML_TEMPERATURE_GPU
                        )
                    )
                except Exception:
                    temp = None

                # Row remap
                try:
                    remap = pynvml.nvmlDeviceGetRowRemapperHistogram(handle)
                    row_avail = remap.histogram[
                        0
                    ]  # first bucket = remappable rows remaining
                except Exception:
                    row_avail = None

                # PCIe link info
                try:
                    gen_cur = pynvml.nvmlDeviceGetCurrPcieLinkGeneration(handle)
                    gen_max = pynvml.nvmlDeviceGetMaxPcieLinkGeneration(handle)
                    width_cur = pynvml.nvmlDeviceGetCurrPcieLinkWidth(handle)
                    width_max = pynvml.nvmlDeviceGetMaxPcieLinkWidth(handle)
                except Exception:
                    gen_cur = gen_max = width_cur = width_max = None

                tracker.observe(
                    i,
                    xid=xid,
                    sbe_total=sbe,
                    dbe_total=dbe,
                    temperature=temp,
                    row_remap_avail=row_avail,
                )
                m = tracker.compute(
                    i,
                    uuid,
                    model,
                    pcie_gen_current=gen_cur,
                    pcie_gen_max=gen_max,
                    pcie_width_current=width_cur,
                    pcie_width_max=width_max,
                )
                metrics_list.append(m)
            except Exception as exc:
                logger.warning("GPU %d health collection error: %s", i, exc)

        if metrics_list:
            log_time = obj.clock.unixtime()
            sink_impl.write(
                Log(ts=log_time, message=metrics_list),
                additional_params=SinkAdditionalParams(data_type=DataType.METRIC),
            )
            logger.debug("Emitted fleet health for %d GPU(s)", len(metrics_list))
        obj.clock.sleep(push_interval)

    pynvml.nvmlShutdown()
    if hasattr(sink_impl, "shutdown"):
        sink_impl.shutdown()
