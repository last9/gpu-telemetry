# Copyright (c) Meta Platforms, Inc. and affiliates.
# Copyright (c) Last9, Inc.
from dataclasses import dataclass
from typing import Optional

from l9gpu.schemas.device_metrics import DeviceMetrics


@dataclass
class IndexedDeviceMetrics(DeviceMetrics):
    gpu_index: Optional[int] = None
    gpu_uuid: Optional[str] = None  # e.g. "GPU-0f12ab34-..."
    gpu_model: Optional[str] = None  # e.g. "Tesla T4"

    @property
    def prefix(self) -> str:
        return "l9gpu.gpu.{}.".format(self.gpu_index)
