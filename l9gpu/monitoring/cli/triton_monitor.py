#!/usr/bin/env python3
# Copyright (c) Last9, Inc.
"""CLI command for scraping Triton Inference Server and publishing inference metrics."""

import itertools
import logging
import socket
from dataclasses import dataclass, field
from typing import Collection, Mapping, Optional

import click
from l9gpu.exporters import registry
from l9gpu.monitoring import triton_monitor
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

LOGGER_NAME = "triton_monitor"
logger = logging.getLogger(LOGGER_NAME)


@dataclass
class CliObjectImpl:
    registry: Mapping[str, Factory[SinkImpl]] = field(default_factory=lambda: registry)
    clock: Clock = field(default_factory=ClockImpl)

    def format_epilog(self) -> str:
        return get_docs_for_registry(self.registry) + get_docs_for_references(
            [
                "https://docs.nvidia.com/deeplearning/triton-inference-server/user-guide/docs/user_guide/metrics.html"
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
    "--triton-endpoint",
    default="http://localhost:8002/metrics",
    show_default=True,
    help="Triton Inference Server Prometheus endpoint URL.",
)
@click.option(
    "--push-interval",
    type=click.IntRange(min=1),
    default=30,
    show_default=True,
    help="Interval in seconds between metric pushes.",
)
@click.option(
    "--emit-genai-namespace",
    is_flag=True,
    default=False,
    help="Also emit metrics under gen_ai.* OTel semantic conventions (opt-in).",
)
@once_option
@click.pass_obj
@typechecked
def main(
    obj: CliObjectImpl,
    cluster: Optional[str],
    sink: str,
    sink_opts: Collection[str],
    triton_endpoint: str,
    push_interval: int,
    once: bool,
    emit_genai_namespace: bool,
) -> None:
    """Scrape Triton Inference Server and publish per-model metrics (latency, throughput, queue, batch size)."""
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

    prev_state: Optional[triton_monitor.TritonCounterState] = None

    for _ in obj.looptimes(once):
        metrics_list, prev_state = triton_monitor.scrape_triton(
            triton_endpoint,
            prev_state,
            float(push_interval),
        )
        if metrics_list:
            log_time = obj.clock.unixtime()
            sink_impl.write(
                Log(ts=log_time, message=metrics_list),
                additional_params=SinkAdditionalParams(
                    data_type=DataType.METRIC, emit_genai_namespace=emit_genai_namespace
                ),
            )
            logger.debug("Emitted Triton metrics for %d model(s)", len(metrics_list))
        obj.clock.sleep(push_interval)

    if hasattr(sink_impl, "shutdown"):
        sink_impl.shutdown()
