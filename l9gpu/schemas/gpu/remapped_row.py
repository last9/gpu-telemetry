# Copyright (c) Meta Platforms, Inc. and affiliates.
# Copyright (c) Last9, Inc.
from dataclasses import dataclass


@dataclass
class RemappedRowInfo:
    correctable: int
    uncorrectable: int
    pending: int
    failure: int
