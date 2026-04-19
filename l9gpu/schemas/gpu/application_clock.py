# Copyright (c) Meta Platforms, Inc. and affiliates.
# Copyright (c) Last9, Inc.
from dataclasses import dataclass


@dataclass
class ApplicationClockInfo:
    graphics_freq: int
    memory_freq: int
