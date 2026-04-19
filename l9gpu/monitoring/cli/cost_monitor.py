#!/usr/bin/env python3
# Copyright (c) Last9, Inc.
"""CLI command for GPU cost and carbon analytics."""

import itertools
import logging
import socket
from dataclasses import dataclass, field
from typing import Collection, Mapping, Optional

import click
from l9gpu.exporters import registry
from l9gpu.monitoring import cost_monitor, vllm_monitor
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
from l9gpu.monitoring.sink.protocol import DataType, SinkAdditionalParams, SinkImpl
from l9gpu.monitoring.sink.utils import Factory
from l9gpu.schemas.log import Log
from omegaconf import OmegaConf as oc
from typeguard import typechecked

LOGGER_NAME = "cost_monitor"
logger = logging.getLogger(LOGGER_NAME)


@dataclass
class CliObjectImpl:
    registry: Mapping[str, Factory[SinkImpl]] = field(default_factory=lambda: registry)
    clock: Clock = field(default_factory=ClockImpl)

    def format_epilog(self) -> str:
        return get_docs_for_registry(self.registry) + get_docs_for_references(
            [
                "https://instances.vantage.sh",
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
    "--cost-per-gpu-hour",
    type=float,
    default=None,
    help="On-demand cost per GPU per hour (USD). Overrides auto-detect.",
)
@click.option(
    "--instance-type",
    default=None,
    help="EC2 instance type for pricing lookup (e.g. p5.48xlarge). Overrides auto-detect.",
)
@click.option(
    "--vllm-endpoint",
    default=None,
    help="vLLM Prometheus endpoint to read token throughput for cost/token metrics.",
)
@click.option(
    "--idle-threshold",
    type=float,
    default=0.05,
    show_default=True,
    help="GPU utilization fraction below which a GPU is considered idle.",
)
@click.option(
    "--co2-grams-per-kwh",
    type=float,
    default=None,
    help="Grid carbon intensity (gCO2/kWh) for emissions calculation. 0=disabled.",
)
@click.option(
    "--pue",
    type=float,
    default=1.0,
    show_default=True,
    help="Power Usage Effectiveness multiplier for carbon calc (1.0 = ideal).",
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
    cost_per_gpu_hour: Optional[float],
    instance_type: Optional[str],
    vllm_endpoint: Optional[str],
    idle_threshold: float,
    co2_grams_per_kwh: Optional[float],
    pue: float,
    push_interval: int,
    once: bool,
) -> None:
    """Publish GPU cost/token, tokens/watt, idle cost, and carbon emission metrics."""
    try:
        import pynvml  # type: ignore

        pynvml.nvmlInit()
    except Exception as exc:
        raise click.UsageError(f"NVML not available: {exc}")

    # Resolve cost per GPU hour
    if cost_per_gpu_hour is None:
        it = instance_type or cost_monitor.detect_instance_type()
        if it:
            cost_per_gpu_hour = cost_monitor.get_cost_per_gpu_hour(it)
            if cost_per_gpu_hour:
                logger.info("Auto-detected %s → $%.4f/GPU/hr", it, cost_per_gpu_hour)
    if cost_per_gpu_hour is None:
        raise click.UsageError(
            "Cannot determine GPU cost. Set --cost-per-gpu-hour or run on EC2."
        )

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

    device_count = pynvml.nvmlDeviceGetCount()
    vllm_state: Optional[vllm_monitor.CounterState] = None

    for _ in obj.looptimes(once):
        # Optionally scrape vLLM for token throughput
        prompt_tps: Optional[float] = None
        gen_tps: Optional[float] = None
        if vllm_endpoint:
            vllm_metrics, vllm_state = vllm_monitor.scrape_vllm(
                vllm_endpoint, vllm_state, float(push_interval)
            )
            prompt_tps = vllm_metrics.prompt_tokens_per_sec
            gen_tps = vllm_metrics.generation_tokens_per_sec

        metrics_list = []
        for i in range(device_count):
            try:
                handle = pynvml.nvmlDeviceGetHandleByIndex(i)
                try:
                    power_mw = pynvml.nvmlDeviceGetPowerUsage(handle)
                    power_w = power_mw / 1000.0
                except Exception:
                    power_w = None
                try:
                    util = pynvml.nvmlDeviceGetUtilizationRates(handle).gpu / 100.0
                except Exception:
                    util = None

                m = cost_monitor.compute_cost_metrics(
                    gpu_index=i,
                    power_draw_watts=power_w,
                    gpu_util=util,
                    prompt_tokens_per_sec=prompt_tps,
                    generation_tokens_per_sec=gen_tps,
                    cost_per_gpu_hour=cost_per_gpu_hour,
                    idle_threshold=idle_threshold,
                    co2_grams_per_kwh=co2_grams_per_kwh,
                    pue=pue,
                )
                metrics_list.append(m)
            except Exception as exc:
                logger.warning("GPU %d cost collection error: %s", i, exc)

        if metrics_list:
            log_time = obj.clock.unixtime()
            sink_impl.write(
                Log(ts=log_time, message=metrics_list),
                additional_params=SinkAdditionalParams(data_type=DataType.METRIC),
            )
            logger.debug("Emitted cost metrics for %d GPU(s)", len(metrics_list))
        obj.clock.sleep(push_interval)

    pynvml.nvmlShutdown()
    if hasattr(sink_impl, "shutdown"):
        sink_impl.shutdown()
