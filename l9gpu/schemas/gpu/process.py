# Copyright (c) Meta Platforms, Inc. and affiliates.
# Copyright (c) Last9, Inc.
from dataclasses import dataclass


@dataclass
class ProcessInfo:
    pid: int
    usedGpuMemory: int  # noqa: N815
