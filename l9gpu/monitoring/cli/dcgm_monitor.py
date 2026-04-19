#!/usr/bin/env python3
# Copyright (c) Last9, Inc.
"""CLI command for scraping dcgm-exporter and publishing DCGM profiling metrics."""

import itertools
import logging
import socket
from dataclasses import dataclass, field
from typing import Collection, Mapping, Optional

import click
from l9gpu.exporters import registry
from l9gpu.monitoring import dcgm_monitor
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

LOGGER_NAME = "dcgm_monitor"
logger = logging.getLogger(LOGGER_NAME)


@dataclass
class CliObjectImpl:
    registry: Mapping[str, Factory[SinkImpl]] = field(default_factory=lambda: registry)
    clock: Clock = field(default_factory=ClockImpl)

    def format_epilog(self) -> str:
        return get_docs_for_registry(self.registry) + get_docs_for_references(
            ["https://github.com/NVIDIA/dcgm-exporter"]
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
    "--dcgm-endpoint",
    default="http://localhost:9400/metrics",
    show_default=True,
    help="dcgm-exporter Prometheus endpoint URL.",
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
    dcgm_endpoint: str,
    push_interval: int,
    once: bool,
) -> None:
    """Scrape dcgm-exporter and publish DCGM GPU profiling metrics (SM active, tensor core, FP pipes, DRAM)."""
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

    for _ in obj.looptimes(once):
        metrics_list = dcgm_monitor.scrape_dcgm(dcgm_endpoint)
        if metrics_list:
            log_time = obj.clock.unixtime()
            sink_impl.write(
                Log(ts=log_time, message=metrics_list),
                additional_params=SinkAdditionalParams(data_type=DataType.METRIC),
            )
            logger.debug(
                "Emitted DCGM profiling metrics for %d GPU(s)", len(metrics_list)
            )
        obj.clock.sleep(push_interval)

    if hasattr(sink_impl, "shutdown"):
        sink_impl.shutdown()
