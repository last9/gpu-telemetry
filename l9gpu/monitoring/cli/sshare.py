# Copyright (c) Meta Platforms, Inc. and affiliates.
# Copyright (c) Last9, Inc.
import logging
from dataclasses import dataclass, field
from typing import (
    Any,
    Collection,
    Generator,
    Hashable,
    Literal,
    Mapping,
    Optional,
    Protocol,
    runtime_checkable,
)

import click
import os
from l9gpu.exporters import registry

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
from l9gpu.monitoring.clock import Clock, ClockImpl, unixtime_to_pacific_datetime
from l9gpu.monitoring.dataclass_utils import instantiate_dataclass
from l9gpu.monitoring.sink.protocol import DataType, SinkAdditionalParams, SinkImpl
from l9gpu.monitoring.sink.utils import Factory, HasRegistry
from l9gpu.monitoring.slurm.client import SlurmCliClient, SlurmClient
from l9gpu.monitoring.slurm.derived_cluster import get_derived_cluster
from l9gpu.monitoring.utils.monitor import run_data_collection_loop
from l9gpu.schemas.slurm.sshare import SsharePayload, SshareRow
from typeguard import typechecked

LOGGER_NAME = "sshare"
logger = logging.getLogger(LOGGER_NAME)


def sshare_iterator(
    slurm_client: SlurmClient,
    cluster: str,
    collection_date: str,
    collection_unixtime: int,
    heterogeneous_cluster_v1: bool,
) -> Generator[SsharePayload, None, None]:
    get_stdout = iter(slurm_client.sshare())
    field_names = next(get_stdout).strip().split("|")
    for sshare_line in get_stdout:
        values = sshare_line.strip().split("|")
        raw_data: dict[Hashable, Any] = dict(zip(field_names, values))
        sshare_row = instantiate_dataclass(SshareRow, raw_data, logger=logger)
        derived_cluster = get_derived_cluster(
            data=raw_data,
            heterogeneous_cluster_v1=heterogeneous_cluster_v1,
            cluster=cluster,
        )
        yield SsharePayload(
            ds=collection_date,
            collection_unixtime=collection_unixtime,
            cluster=cluster,
            derived_cluster=derived_cluster,
            sshare=sshare_row,
        )


def collect_sshare(
    clock: Clock,
    cluster: str,
    slurm_client: SlurmClient,
    heterogeneous_cluster_v1: bool,
) -> Generator[SsharePayload, None, None]:

    log_time = clock.unixtime()
    collection_date = unixtime_to_pacific_datetime(log_time).strftime("%Y-%m-%d")

    records = sshare_iterator(
        slurm_client,
        cluster,
        collection_date,
        collection_unixtime=log_time,
        heterogeneous_cluster_v1=heterogeneous_cluster_v1,
    )
    return records


@runtime_checkable
class CliObject(HasRegistry[SinkImpl], Protocol):
    @property
    def clock(self) -> Clock: ...

    def cluster(self) -> str: ...
    @property
    def slurm_client(self) -> SlurmClient: ...


@dataclass
class CliObjectImpl:
    registry: Mapping[str, Factory[SinkImpl]] = field(default_factory=lambda: registry)
    clock: Clock = field(default_factory=ClockImpl)
    slurm_client: SlurmClient = field(default_factory=SlurmCliClient)

    def cluster(self) -> str:
        return os.environ.get("L9GPU_CLUSTER_NAME", "")


# construct at module-scope because printing sink documentation relies on the object
_default_obj: CliObject = CliObjectImpl()


@click_default_cmd(context_settings={"obj": _default_obj})
@cluster_option
@sink_option
@sink_opts_option
@log_level_option
@log_folder_option
@stdout_option
@heterogeneous_cluster_v1_option
@interval_option(default=300)
@once_option
@retries_option
@dry_run_option
@chunk_size_option
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
    interval: int,
    once: bool,
    retries: int,
    dry_run: bool,
    chunk_size: int,
) -> None:
    """
    Collects slurm fair-share scheduling data (sshare) and sends to sink.
    """

    def collect_sshare_callable(
        cluster: str, interval: int, logger: logging.Logger
    ) -> Generator[SsharePayload, None, None]:
        return collect_sshare(
            clock=obj.clock,
            cluster=cluster,
            slurm_client=obj.slurm_client,
            heterogeneous_cluster_v1=heterogeneous_cluster_v1,
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
                collect_sshare_callable,
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
