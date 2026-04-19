# Copyright (c) Meta Platforms, Inc. and affiliates.
# Copyright (c) Last9, Inc.
from dataclasses import dataclass
from typing import Optional


@dataclass
class GPUUtilization:
    gpu: int
    memory: Optional[int] = None
