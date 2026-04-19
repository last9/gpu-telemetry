# Copyright (c) Meta Platforms, Inc. and affiliates.
# Copyright (c) Last9, Inc.
from dataclasses import dataclass

from typing import Hashable

from l9gpu.schemas.slurm.derived_cluster import DerivedCluster


@dataclass(kw_only=True)
class SacctmgrUserPayload(DerivedCluster):
    ds: str
    cluster: str
    sacctmgr_user: dict[Hashable, str]
