#!/usr/bin/env python3
# Copyright (c) Last9, Inc.
"""Computes Intel Gaudi GPU metrics averaged over a window and publishes metrics."""

import itertools
import json
import logging
import os
import socket
from dataclasses import asdict, dataclass, field
from typing import (
    Callable,
    Collection,
    Dict,
    Iterable,
    Literal,
    Mapping,
    Optional,
    Protocol,
    runtime_checkable,
    Tuple,
)

import click
from l9gpu.exporters import registry
from l9gpu.monitoring.accumulate import Accumulator
from l9gpu.monitoring.click import (
    click_default_cmd,
    cluster_option,
    DynamicEpilogCommand,
    EpilogFormatter,
    get_docs_for_references,
    get_docs_for_registry,
    heterogeneous_cluster_v1_option,
    interval_option,
    log_folder_option,
    log_level_option,
    once_option,
    sink_option,
    sink_opts_option,
    stdout_option,
)
from l9gpu.monitoring.clock import Clock, ClockImpl
from l9gpu.monitoring.dataclass_utils import max_fields
from l9gpu.monitoring.device_telemetry_client import (
    DeviceTelemetryClient,
)
from l9gpu.monitoring.device_telemetry_gaudi import (
    GaudiDeviceTelemetryClient,
    GaudiGPUDevice,
)
from l9gpu.monitoring.sink.protocol import DataType, SinkAdditionalParams, SinkImpl
from l9gpu.monitoring.sink.utils import Factory, HasRegistry
from l9gpu.monitoring.utils import error
from l9gpu.monitoring.utils.monitor import init_logger
from l9gpu.monitoring.utils.shell import get_command_output
from l9gpu.schemas.gaudi_device_metrics import (
    GaudiDeviceMetrics,
    GaudiDevicePlusJobMetrics,
    IndexedGaudiDeviceMetrics,
)
from l9gpu.schemas.host_metrics import HostMetrics
from l9gpu.schemas.job_info import JobInfo
from l9gpu.schemas.log import Log
from omegaconf import OmegaConf as oc
from typeguard import typechecked

LOGGER_NAME = "gaudi_monitor"

log_error = error.log_error(logger_name=LOGGER_NAME)
logger: logging.Logger  # initialization in main()


def get_device_metrics_basic(handle: GaudiGPUDevice) -> GaudiDeviceMetrics:
    """Retrieve Gaudi device metrics via hl-smi."""
    metrics = GaudiDeviceMetrics(mem_used_percent=-1)

    utilization = log_error(handle.get_utilization_rates)()
    if utilization is not None:
        metrics.gpu_util = utilization.gpu
        metrics.mem_util = utilization.memory

    memory_info = log_error(handle.get_memory_info)()
    if memory_info is not None and memory_info.total > 0:
        metrics.mem_used_percent = int(memory_info.used / memory_info.total * 100)

    metrics.temperature = log_error(handle.get_temperature)()
    metrics.power_draw = log_error(handle.get_power_usage)()

    metrics.retired_pages_count_single_bit = 0
    metrics.retired_pages_count_double_bit = 0

    # Gaudi-specific metrics
    metrics.network_rx_bandwidth = log_error(handle.get_network_rx_bandwidth)()
    metrics.network_tx_bandwidth = log_error(handle.get_network_tx_bandwidth)()
    metrics.rows_replaced = log_error(handle.get_rows_replaced)()
    metrics.rows_pending = log_error(handle.get_rows_pending)()

    return metrics


ProcessId = int
Env = Mapping[str, str]
EnvReader = Callable[[ProcessId], Env]


def read_environ_from_proc(
    process_id: int,
    *,
    run_cmd: Callable = get_command_output,
) -> Dict[str, str]:
    cmd = ["sudo", "cat", f"/proc/{process_id}/environ"]
    env_vars_raw = run_cmd(cmd).split("\x00")
    return dict(v.split("=", maxsplit=1) for v in env_vars_raw if v != "")


@log_error
def retrieve_job_on_gpu(
    handle: GaudiGPUDevice,
    *,
    env_reader: EnvReader = read_environ_from_proc,
) -> Optional[JobInfo]:
    # Gaudi does not expose compute processes; return None (no job correlation)
    return None


def get_ram_utilization(*, get_command_output: Callable = get_command_output) -> float:
    text = get_command_output(["free", "-m"])
    lines = text.split("\n")
    header = " ".join(lines[0].split())
    ram_info = " ".join(lines[1].split())
    ram_info = ram_info[ram_info.find(":") + 2 :]  # noqa: E203
    header_parts = header.split(" ")
    ram_info_parts = ram_info.split(" ")
    ram_stats = {}
    for i, key in enumerate(header_parts):
        ram_stats[key] = int(ram_info_parts[i])
    return ram_stats["used"] / ram_stats["total"]


def compute_host_level_metrics(
    metrics: Iterable[GaudiDeviceMetrics],
    get_ram_utilization_fn: Callable[[], float],
) -> HostMetrics:
    gpu_utils = list(filter(None, (metric.gpu_util for metric in metrics)))
    max_gpu_util = max(gpu_utils, default=0)
    min_gpu_util = min(gpu_utils, default=0)
    avg_gpu_util = sum(gpu_utils) / len(gpu_utils) if len(gpu_utils) > 0 else 0.0
    ram_util = get_ram_utilization_fn()
    return HostMetrics(
        max_gpu_util=max_gpu_util,
        min_gpu_util=min_gpu_util,
        avg_gpu_util=avg_gpu_util,
        ram_util=ram_util,
    )


def log_setup(
    log_folder: str,
    hostname: str,
    device_count: int,
    log_stdout: bool,
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
) -> Tuple[logging.Logger, logging.Handler, list]:
    logger, handler = init_logger(
        logger_name=LOGGER_NAME,
        log_dir=os.path.join(log_folder, LOGGER_NAME + "_logs"),
        log_name=hostname + ".log",
        log_formatter=logging.Formatter("[%(asctime)s] - [General] - %(message)s"),
        log_stdout=log_stdout,
        log_level=getattr(logging, log_level),
    )
    gpu_specific_formatter = [
        logging.Formatter("[%(asctime)s] - [Gaudi# {}] - %(message)s".format(idx))
        for idx in range(device_count)
    ]
    return logger, handler, gpu_specific_formatter


@runtime_checkable
class CliObject(EpilogFormatter, HasRegistry[SinkImpl], Protocol):
    def get_device_telemetry(self) -> DeviceTelemetryClient: ...

    @property
    def clock(self) -> Clock: ...

    def read_env(self, process_id: int) -> Env: ...

    def get_ram_utilization(self) -> float: ...

    def get_hostname(self) -> str: ...

    def looptimes(self, once: bool) -> Iterable[int]: ...


@dataclass
class CliObjectImpl:
    registry: Mapping[str, Factory[SinkImpl]] = field(default_factory=lambda: registry)
    clock: Clock = field(default_factory=ClockImpl)

    def get_device_telemetry(self) -> DeviceTelemetryClient:
        return GaudiDeviceTelemetryClient()

    def read_env(self, process_id: int) -> Env:
        return read_environ_from_proc(process_id)

    def get_ram_utilization(self) -> float:
        return get_ram_utilization()

    def get_hostname(self) -> str:
        return socket.gethostname().replace(".maas", "")

    def format_epilog(self) -> str:
        return get_docs_for_registry(self.registry) + get_docs_for_references(
            [
                "https://omegaconf.readthedocs.io/en/2.2_branch/usage.html#from-a-dot-list"
            ]
        )

    def looptimes(self, once: bool) -> Iterable[int]:
        if once:
            return range(1)
        return itertools.count(0)


class CustomCommand(
    DynamicEpilogCommand[CliObject],
    obj_cls=CliObject,  # type: ignore[type-abstract]
):
    pass


_default_obj: CliObject = CliObjectImpl()


@click_default_cmd(cls=CustomCommand, context_settings={"obj": _default_obj})
@cluster_option
@sink_option
@sink_opts_option
@log_level_option
@log_folder_option
@stdout_option
@heterogeneous_cluster_v1_option
@click.option(
    "--push-interval",
    type=click.IntRange(min=1),
    default=60,
    help="The interval in seconds to push metrics.",
)
@click.option(
    "--collect-interval",
    type=click.IntRange(min=1),
    default=10,
    help="The interval in seconds to collect telemetry data.",
)
@interval_option(default=90)
@click.option(
    "--stdout",
    is_flag=True,
    help="Whether to display metric information to stdout.",
)
@click.option(
    "--hl-smi-path",
    type=str,
    default="hl-smi",
    show_default=True,
    help="Path to the hl-smi binary.",
)
@click.option(
    "--vendor",
    type=str,
    default="intel",
    show_default=True,
    help="GPU vendor name reported in metric resource attributes.",
)
@once_option
@click.pass_obj
@typechecked
def main(
    obj: CliObject,
    cluster: Optional[str],
    sink: str,
    sink_opts: Collection[str],
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    log_folder: str,
    heterogeneous_cluster_v1: bool,
    push_interval: int,
    collect_interval: int,
    stdout: bool,
    interval: int,
    hl_smi_path: str,
    vendor: str,
    once: bool,
) -> None:
    """Script for reading Intel Gaudi GPU metrics on the node via hl-smi."""
    global logger

    device_telemetry = obj.get_device_telemetry()
    device_count = device_telemetry.get_device_count()
    hostname = obj.get_hostname()

    logger, log_handler, gpu_specific_formatter = log_setup(
        log_folder, hostname, device_count, stdout, log_level
    )

    # Inject GPU vendor, host.name, and (optionally) k8s.cluster.name as resource attributes
    # for BOTH the metric and log signals so Last9 can correlate across them.
    base_resource = [
        f"gpu.vendor={vendor}",
        f"host.name={hostname}",
    ]
    if cluster:
        base_resource.append(f"k8s.cluster.name={cluster}")

    augmented_sink_opts = list(sink_opts)
    for attr in base_resource:
        augmented_sink_opts.append(f"metric_resource_attributes.{attr}")
        augmented_sink_opts.append(f"log_resource_attributes.{attr}")
    try:
        sink_impl = obj.registry[sink](**oc.from_dotlist(augmented_sink_opts))
    except ValueError as e:
        raise click.UsageError(str(e))

    for _ in obj.looptimes(once):
        run_st_time = obj.clock.monotonic()

        job_per_device_collection: Dict[int, JobInfo] = {
            gpu: JobInfo() for gpu in range(device_count)
        }
        accumulators = [
            Accumulator[GaudiDeviceMetrics](max_fields(GaudiDeviceMetrics))
            for _ in range(device_count)
        ]

        while obj.clock.monotonic() - run_st_time < push_interval:
            for device_index, accumulator in enumerate(accumulators):
                log_handler.setFormatter(gpu_specific_formatter[device_index])

                handle = log_error(device_telemetry.get_device_by_index)(device_index)
                if handle is None:
                    continue

                accumulator.tell(get_device_metrics_basic(handle))

            obj.clock.sleep(collect_interval)

        log_time = obj.clock.unixtime()
        indexed_device_metrics = []

        for index, metrics in enumerate(a.ask() for a in accumulators):
            indexed_device_metrics.append(
                IndexedGaudiDeviceMetrics(gpu_index=index, **asdict(metrics))
            )

            device_plus_job_metrics = GaudiDevicePlusJobMetrics(
                gpu_id=index,
                hostname=hostname,
                **asdict(metrics),
                **asdict(job_per_device_collection[index]),
            )

            sink_impl.write(
                Log(ts=log_time, message=[device_plus_job_metrics]),
                additional_params=SinkAdditionalParams(data_type=DataType.LOG),
            )
            logger.debug(json.dumps(asdict(device_plus_job_metrics), sort_keys=True))

        host_level_metrics = compute_host_level_metrics(
            (a.ask() for a in accumulators), obj.get_ram_utilization
        )
        logger.debug(json.dumps(asdict(host_level_metrics), sort_keys=True))

        sink_impl.write(
            Log(
                ts=log_time,
                message=indexed_device_metrics + [host_level_metrics],
            ),
            additional_params=SinkAdditionalParams(data_type=DataType.METRIC),
        )

        obj.clock.sleep(max(0, interval - (obj.clock.monotonic() - run_st_time)))

    if hasattr(sink_impl, "shutdown"):
        sink_impl.shutdown()
