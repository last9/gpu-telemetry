# Copyright (c) Meta Platforms, Inc. and affiliates.
# Copyright (c) Last9, Inc.
from dataclasses import dataclass
from typing import Iterable

from l9gpu.schemas.slurm.sinfo_node import SinfoNode


@dataclass
class Sinfo:
    nodes: Iterable[SinfoNode]
