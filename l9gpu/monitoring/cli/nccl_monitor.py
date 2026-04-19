#!/usr/bin/env python3
# Copyright (c) Last9, Inc.
"""CLI command for NCCL Inspector log parsing and collective communication monitoring."""

import itertools
import logging
import socket
from dataclasses import dataclass, field
from typing import Collection, Mapping, Optional

import click
from l9gpu.exporters import registry
from l9gpu.monitoring import nccl_monitor
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

LOGGER_NAME = "nccl_monitor"
logger = logging.getLogger(LOGGER_NAME)


@dataclass
class CliObjectImpl:
    registry: Mapping[str, Factory[SinkImpl]] = field(default_factory=lambda: registry)
    clock: Clock = field(default_factory=ClockImpl)

    def format_epilog(self) -> str:
        return get_docs_for_registry(self.registry) + get_docs_for_references(
            [
                "https://developer.nvidia.com/blog/enhancing-communication-observability-of-ai-workloads-with-nccl-inspector",
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
    "--nccl-log-path",
    default="/tmp/nccl_inspector.jsonl",
    show_default=True,
    envvar="NCCL_INSPECTOR_LOG",
    help="Path to NCCL Inspector JSON log file (set NCCL_INSPECTOR_LOG env var on training process).",
)
@click.option(
    "--straggler-threshold-ms",
    type=float,
    default=1000.0,
    show_default=True,
    help="Duration (ms) above median at which a rank is flagged as a straggler.",
)
@click.option(
    "--push-interval",
    type=click.IntRange(min=1),
    default=30,
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
    nccl_log_path: str,
    straggler_threshold_ms: float,
    push_interval: int,
    once: bool,
) -> None:
    """Parse NCCL Inspector logs and publish collective communication metrics (bandwidth, latency, straggler detection)."""
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

    file_position = 0

    for _ in obj.looptimes(once):
        metrics_list, file_position = nccl_monitor.tail_and_parse(
            nccl_log_path,
            file_position,
            straggler_threshold_ms=straggler_threshold_ms,
        )
        if metrics_list:
            log_time = obj.clock.unixtime()
            sink_impl.write(
                Log(ts=log_time, message=metrics_list),
                additional_params=SinkAdditionalParams(data_type=DataType.METRIC),
            )
            logger.debug("Emitted %d NCCL collective records", len(metrics_list))
        obj.clock.sleep(push_interval)

    if hasattr(sink_impl, "shutdown"):
        sink_impl.shutdown()
