# Copyright (c) Last9, Inc.
"""Gaudi-specific device metrics extending the base DeviceMetrics dataclass."""

from dataclasses import dataclass
from typing import List, Optional

from l9gpu.schemas.device_metrics import DeviceMetrics
from l9gpu.schemas.job_info import JobInfo


@dataclass
class GaudiDeviceMetrics(DeviceMetrics):
    # Per-port RX bandwidth in bytes/sec (up to 24×200 GbE ports on Gaudi 3)
    network_rx_bandwidth: Optional[List[int]] = None
    # Per-port TX bandwidth in bytes/sec
    network_tx_bandwidth: Optional[List[int]] = None
    # Number of DRAM rows replaced due to errors
    rows_replaced: Optional[int] = None
    # Number of DRAM rows pending replacement
    rows_pending: Optional[int] = None


@dataclass
class IndexedGaudiDeviceMetrics(GaudiDeviceMetrics):
    """Gaudi device metrics with gpu_index for the METRIC export path."""

    gpu_index: Optional[int] = None


@dataclass
class GaudiDevicePlusJobMetrics(GaudiDeviceMetrics, JobInfo):
    gpu_id: Optional[int] = None
    hostname: Optional[str] = None
    job_cpus_per_gpu: Optional[float] = None
