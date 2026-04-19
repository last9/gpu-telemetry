# Copyright (c) Meta Platforms, Inc. and affiliates.
# Copyright (c) Last9, Inc.
from dataclasses import dataclass, fields
from typing import cast, Optional, TYPE_CHECKING

from l9gpu.schemas.job_info import JobInfo
from typeguard import typechecked

if TYPE_CHECKING:
    from _typeshed import DataclassInstance


@dataclass
class DeviceMetrics:
    mem_util: Optional[int] = None
    mem_used_percent: Optional[int] = None
    gpu_util: Optional[int] = None
    temperature: Optional[int] = None
    power_draw: Optional[int] = None
    power_used_percent: Optional[int] = None
    retired_pages_count_single_bit: Optional[int] = None
    retired_pages_count_double_bit: Optional[int] = None
    # Gap 1 — absolute VRAM values (bytes)
    mem_used_bytes: Optional[int] = None
    mem_total_bytes: Optional[int] = None
    mem_free_bytes: Optional[int] = None
    # Gap 2 — GPU clock frequencies (MHz)
    clock_graphics_mhz: Optional[int] = None
    clock_memory_mhz: Optional[int] = None
    # Gap 3 — NVLink aggregate bandwidth (bytes/s); None on non-NVLink nodes
    nvlink_tx_bandwidth: Optional[int] = None
    nvlink_rx_bandwidth: Optional[int] = None
    # Gap 4 — ECC volatile errors (reset each driver session; early degradation signal)
    ecc_errors_volatile_correctable: Optional[int] = None
    ecc_errors_volatile_uncorrectable: Optional[int] = None
    # Gap 5 — Clock throttle reasons (bitmask: why clock is throttled)
    throttle_reason: Optional[int] = None
    # Gap 6 — GPU P-state (0=full compute, 8=idle)
    power_state: Optional[int] = None
    # Gap 7 — PCIe throughput (bytes/s)
    pcie_rx_bytes: Optional[int] = None
    pcie_tx_bytes: Optional[int] = None
    # Gap 8 — Fan speed (0–100%)
    fan_speed_percent: Optional[int] = None
    # Gap 9 — Encode / decode engine utilization (0–100)
    enc_util: Optional[int] = None
    dec_util: Optional[int] = None
    # Gap 10 — XID error count (cumulative; reliability signal)
    xid_errors: Optional[int] = None
    # Gap 11 — PCIe replay counter (cumulative; link health signal)
    pcie_replay_count: Optional[int] = None
    # Gap 12 — Cumulative energy consumption (mJ)
    total_energy_mj: Optional[int] = None
    # Gap 13 — Named throttle reason booleans (0 or 1; expanded from bitmask)
    throttle_power_software: Optional[int] = None
    throttle_temp_hardware: Optional[int] = None
    throttle_temp_software: Optional[int] = None
    throttle_syncboost: Optional[int] = None

    # --- Phase 17: Grace-Hopper / Blackwell unified memory ---
    # On GH200/GB200, CPU and GPU share a single coherent memory pool.
    # Standard NVML mem_used_bytes / mem_total_bytes may return 0 or mirrored values.
    # When unified memory is detected, these fields replace the discrete VRAM fields.
    # None on standard discrete-GPU systems (backward compatible).
    mem_unified_used_bytes: Optional[int] = None
    mem_unified_total_bytes: Optional[int] = None
    # GPU architecture string (e.g. "hopper", "blackwell", "ampere") — resource attribute
    gpu_architecture: Optional[str] = None

    @typechecked
    def __add__(self, other: JobInfo) -> "DevicePlusJobMetrics":
        dev_job_metrics = DevicePlusJobMetrics()

        for obj in [self, other]:
            for _field in fields(cast(DataclassInstance, obj)):
                setattr(dev_job_metrics, _field.name, getattr(obj, _field.name))

        return dev_job_metrics


@dataclass
class DevicePlusJobMetrics(DeviceMetrics, JobInfo):
    gpu_id: Optional[int] = None
    hostname: Optional[str] = None
    job_cpus_per_gpu: Optional[float] = None
