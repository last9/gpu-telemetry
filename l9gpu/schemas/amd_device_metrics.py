# Copyright (c) Last9, Inc.
"""AMD-specific device metrics extending the base DeviceMetrics dataclass."""

from dataclasses import dataclass
from typing import Dict, List, Optional

from l9gpu.schemas.device_metrics import DeviceMetrics
from l9gpu.schemas.job_info import JobInfo


@dataclass
class AMDDeviceMetrics(DeviceMetrics):
    # Per-link XGMI bandwidth in bytes/sec (8 links on MI300X, MI325X)
    xgmi_link_bandwidth: Optional[List[int]] = None
    # Per-block ECC correctable error counts (40+ blocks on MI300X)
    ecc_per_block: Optional[Dict[str, int]] = None
    # Junction/hotspot temperature in Celsius
    junction_temperature: Optional[int] = None
    # HBM temperature in Celsius
    hbm_temperature: Optional[int] = None


@dataclass
class IndexedAMDDeviceMetrics(AMDDeviceMetrics):
    """AMD device metrics with gpu_index for the METRIC export path."""

    gpu_index: Optional[int] = None


@dataclass
class AMDDevicePlusJobMetrics(AMDDeviceMetrics, JobInfo):
    gpu_id: Optional[int] = None
    hostname: Optional[str] = None
    job_cpus_per_gpu: Optional[float] = None
