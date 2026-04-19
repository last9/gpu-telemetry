# Copyright (c) Meta Platforms, Inc. and affiliates.
# Copyright (c) Last9, Inc.
from dataclasses import dataclass, fields

from l9gpu.monitoring.clock import time_to_time_aware
from l9gpu.monitoring.coerce import maybe_float, maybe_int
from l9gpu.monitoring.slurm.nodelist_parsers import nodelist
from l9gpu.monitoring.slurm.parsing import (
    convert_memory_to_mb,
    parse_gres_or_tres,
    parse_value_from_tres,
)
from l9gpu.schemas.dataclass import parsed_field
from l9gpu.schemas.slurm.derived_cluster import DerivedCluster


@dataclass(kw_only=True)
class JobData(DerivedCluster):
    collection_unixtime: int
    cluster: str
    PENDING_RESOURCES: str
    GPUS_REQUESTED: int | None = parsed_field(
        parser=parse_gres_or_tres, field_name="TRES-PER-NODE"
    )
    MIN_CPUS: int | None = parsed_field(parser=maybe_int, field_name="MINCPUS")
    JOBID: str = parsed_field(parser=str, field_name="JOBARRAYID")
    JOBID_RAW: str = parsed_field(parser=str, field_name="JOBID")
    NAME: str = parsed_field(parser=str)
    TIME_LIMIT: str = parsed_field(parser=str, field_name="TIMELIMIT")
    MIN_MEMORY: int = parsed_field(parser=convert_memory_to_mb, field_name="MINMEMORY")
    COMMAND: str = parsed_field(parser=str)
    PRIORITY: float | None = parsed_field(parser=maybe_float)
    STATE: str = parsed_field(parser=str)
    USER: str = parsed_field(parser=str, field_name="USERNAME")
    CPUS: int | None = parsed_field(parser=maybe_int, field_name="NUMCPUS")
    NODES: int | None = parsed_field(parser=maybe_int, field_name="NUMNODES")
    TIME_LEFT: str = parsed_field(parser=str, field_name="TIMELEFT")
    TIME_USED: str = parsed_field(parser=str, field_name="TIMEUSED")
    NODELIST: list[str] | None = parsed_field(parser=lambda s: nodelist()(s)[0])
    DEPENDENCY: str = parsed_field(parser=str)
    EXC_NODES: list[str] | None = parsed_field(
        parser=lambda s: nodelist()(s)[0], field_name="EXCNODES"
    )
    START_TIME: str = parsed_field(parser=time_to_time_aware, field_name="STARTTIME")
    SUBMIT_TIME: str = parsed_field(parser=time_to_time_aware, field_name="SUBMITTIME")
    ELIGIBLE_TIME: str = parsed_field(
        parser=time_to_time_aware, field_name="ELIGIBLETIME"
    )
    ACCRUE_TIME: str = parsed_field(parser=time_to_time_aware, field_name="ACCRUETIME")
    PENDING_TIME: int | None = parsed_field(parser=maybe_int, field_name="PENDINGTIME")
    COMMENT: str = parsed_field(parser=str)
    PARTITION: str = parsed_field(parser=str)
    ACCOUNT: str = parsed_field(parser=str)
    QOS: str = parsed_field(parser=str)
    REASON: str = parsed_field(parser=str)
    TRES_GPUS_ALLOCATED: int = parsed_field(
        parser=lambda s: parse_value_from_tres(s, "gres/gpu"), field_name="TRES-ALLOC"
    )
    TRES_CPU_ALLOCATED: int = parsed_field(
        parser=lambda s: parse_value_from_tres(s, "cpu"), field_name="TRES-ALLOC"
    )
    TRES_MEM_ALLOCATED: int = parsed_field(
        parser=lambda s: parse_value_from_tres(s, "mem"), field_name="TRES-ALLOC"
    )
    TRES_NODE_ALLOCATED: int = parsed_field(
        parser=lambda s: parse_value_from_tres(s, "node"), field_name="TRES-ALLOC"
    )
    TRES_BILLING_ALLOCATED: int = parsed_field(
        parser=lambda s: parse_value_from_tres(s, "billing"), field_name="TRES-ALLOC"
    )
    RESERVATION: str = parsed_field(parser=str)
    REQUEUE: str = parsed_field(parser=str)
    FEATURE: str = parsed_field(parser=str)
    RESTARTCNT: int = parsed_field(parser=int)
    SCHEDNODES: list[str] | None = parsed_field(parser=lambda s: nodelist()(s)[0])


JOB_DATA_SLURM_FIELDS = list(
    dict.fromkeys(
        [
            f.metadata.get("field_name", f.name)
            for f in fields(JobData)
            if f.metadata.get("slurm_field", False)
        ]
    )
)
