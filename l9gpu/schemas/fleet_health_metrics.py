# Copyright (c) Last9, Inc.
"""Schema for GPU fleet health metrics — predictive failure signals.

These metrics go beyond point-in-time readings to surface trends and
composite health signals used for proactive GPU replacement decisions.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class GPUFleetHealthMetrics:
    """Per-GPU fleet health metrics derived from NVML + sliding-window analysis.

    Collected alongside DeviceMetrics by fleet_health_monitor.
    All rate fields use a configurable sliding window (default: 5 minutes).
    """

    # GPU identity (data-point attributes)
    gpu_index: Optional[int] = None
    gpu_uuid: Optional[str] = None
    gpu_model: Optional[str] = None

    # --- XID errors ---
    # Most recent XID error code (e.g. 79 = GPU fell off bus, 48 = DBE)
    xid_last_error_code: Optional[int] = None
    # XID events per hour over the sliding window (normalized for fleet comparison)
    xid_error_rate: Optional[float] = None

    # --- ECC trends ---
    # Single-bit correctable errors per hour (upward trend = impending failure)
    ecc_sbe_rate: Optional[float] = None
    # Cumulative double-bit uncorrectable errors — any non-zero is critical
    ecc_dbe_total: Optional[int] = None

    # --- Row remapping (HBM health) ---
    # Remaining remappable rows; when 0, next UE forces GPU retirement
    row_remap_available: Optional[int] = None

    # --- PCIe link health ---
    # Current PCIe gen (e.g. 5 expected on H100); downtraining = degraded
    pcie_link_gen_current: Optional[int] = None
    # Current PCIe width (e.g. 16 expected); narrowing = link problem
    pcie_link_width_current: Optional[int] = None
    # 1 when current gen or width < max capability (immediate alert)
    pcie_link_downtraining: Optional[int] = None

    # --- Thermal trend ---
    # Temperature change rate over sliding window (Celsius/minute)
    # >2.0 °C/min suggests cooling failure
    thermal_ramp_rate: Optional[float] = None

    # --- Composite health score ---
    # 0–100; 100 = fully healthy; <80 = warning; <50 = critical
    health_score: Optional[float] = None
