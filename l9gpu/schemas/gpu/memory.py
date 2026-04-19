# Copyright (c) Meta Platforms, Inc. and affiliates.
# Copyright (c) Last9, Inc.
from dataclasses import dataclass


@dataclass
class GPUMemory:
    total: int
    free: int
    used: int
