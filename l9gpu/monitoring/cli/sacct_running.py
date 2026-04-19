# Copyright (c) Meta Platforms, Inc. and affiliates.
# Copyright (c) Last9, Inc.
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from functools import partial
from typing import (
    Collection,
    Generator,
    Literal,
    Mapping,
    Optional,
    Protocol,
    runtime_checkable,
    TYPE_CHECKING,
)

import click
import os
from l9gpu.exporters import registry

from l9gpu.monitoring.cli.slurm_job_monitor import as_messages
from l9gpu.monitoring.click import (
    chunk_size_option,
    click_default_cmd,
    cluster_option,
    dry_run_option,
    heterogeneous_cluster_v1_option,
    interval_option,
    log_folder_option,
    log_level_option,
    once_option,
    retries_option,
    sink_option,
    sink_opts_option,
    stdout_option,
)
from l9gpu.monitoring.clock import Clock, ClockImpl
from l9gpu.monitoring.sink.protocol import DataType, SinkAdditionalParams, SinkImpl
from l9gpu.monitoring.sink.utils import Factory, HasRegistry
from l9gpu.monitoring.slurm.client import SlurmCliClient, SlurmClient
from l9gpu.monitoring.slurm.constants import SLURM_CLI_DELIMITER

from l9gpu.monitoring.slurm.derived_cluster import get_derived_cluster
from l9gpu.monitoring.utils.monitor import run_data_collection_loop
from l9gpu.schemas.slurm.sacct import Sacct
from typeguard import typechecked

if TYPE_CHECKING:
    from _typeshed import DataclassInstance

LOGGER_NAME = "sacct_running"

logger: logging.Logger = logging.getLogger(
    LOGGER_NAME
)  # default logger to be overridden in main()


@runtime_checkable
class CliObject(HasRegistry[SinkImpl], Protocol):
    @property
    def clock(self) -> Clock: ...

    def cluster(self) -> str: ...

    @property
    def slurm_client(self) -> SlurmClient: ...


@dataclass
class CliObjectImpl:
    clock: Clock = field(default_factory=ClockImpl)
    slurm_client: SlurmClient = field(default_factory=SlurmCliClient)
    registry: Mapping[str, Factory[SinkImpl]] = field(default_factory=lambda: registry)

    def cluster(self) -> str:
        return os.environ.get("L9GPU_CLUSTER_NAME", "")


# construct at module-scope because printing sink documentation relies on the object
_default_obj: CliObject = CliObjectImpl()


def get_sacct_running(
    obj: CliObject,
    delimiter: str,
    cluster: str,
    heterogeneous_cluster_v1: bool,
    logger: logging.Logger,
) -> Generator[DataclassInstance, None, None]:
    derived_cluster_fetcher = partial(
        get_derived_cluster,
        cluster=cluster,
        heterogeneous_cluster_v1=heterogeneous_cluster_v1,
    )
    sacct_data = as_messages(
        schema=Sacct,
        delimiter=delimiter,
        lines=obj.slurm_client.sacct_running(),
        derived_cluster_fetcher=derived_cluster_fetcher,
        logger=logger,
    )
    return sacct_data


@click_default_cmd(context_settings={"obj": _default_obj})
@cluster_option
@sink_option
@sink_opts_option
@log_level_option
@log_folder_option
@stdout_option
@heterogeneous_cluster_v1_option
@retries_option
@once_option
@interval_option(default=3600)
@chunk_size_option
@dry_run_option
@click.option(
    "--delimiter",
    default=SLURM_CLI_DELIMITER,
    show_default=True,
    help="ASCII character used to delimit fields when using -p or -P",
)
@click.pass_obj
@typechecked
def main(
    obj: CliObject,
    cluster: Optional[str],
    sink: str,
    sink_opts: Collection[str],
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    log_folder: str,
    stdout: bool,
    heterogeneous_cluster_v1: bool,
    retries: int,
    once: bool,
    interval: int,
    chunk_size: int,
    dry_run: bool,
    delimiter: str,
) -> None:
    """
    Collects slurm running jobs through sacct and sends to sink.
    """

    def get_sacct_running_callable(
        cluster: str, interval: int, logger: logging.Logger
    ) -> Generator[DataclassInstance, None, None]:
        return get_sacct_running(
            obj=obj,
            delimiter=delimiter,
            cluster=cluster,
            heterogeneous_cluster_v1=heterogeneous_cluster_v1,
            logger=logger,
        )

    run_data_collection_loop(
        logger_name=LOGGER_NAME,
        log_folder=log_folder,
        stdout=stdout,
        log_level=log_level,
        cluster=obj.cluster() if cluster is None else cluster,
        clock=obj.clock,
        once=once,
        interval=interval,
        data_collection_tasks=[
            (
                get_sacct_running_callable,
                SinkAdditionalParams(
                    data_type=DataType.LOG,
                    heterogeneous_cluster_v1=heterogeneous_cluster_v1,
                ),
            ),
        ],
        sink=sink,
        sink_opts=sink_opts,
        retries=retries,
        chunk_size=chunk_size,
        dry_run=dry_run,
        registry=obj.registry,
    )
