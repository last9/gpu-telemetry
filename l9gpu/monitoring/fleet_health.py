# Copyright (c) Last9, Inc.
"""GPU fleet health monitoring — sliding-window analysis and health scoring.

Wraps NVML to compute trend metrics (ECC rate, XID rate, thermal ramp)
and a composite health score used for proactive GPU replacement decisions.

Context: XID 79 ("GPU fell off bus") affects 3.2% of H100 fleets in year 1.
Predictive models using ECC trends + thermal ramp achieve 89-96% accuracy
48-72 hours ahead of failure (Meta / Modal GPU fleet research, 2025).
"""

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Sliding window observation: (unix_timestamp, value)
_Observation = Tuple[float, float]


@dataclass
class _GPUWindow:
    """Per-GPU sliding window buffers."""

    xid_events: Deque[_Observation] = field(default_factory=deque)
    sbe_counts: Deque[_Observation] = field(default_factory=deque)
    temperatures: Deque[_Observation] = field(default_factory=deque)
    last_xid: Optional[int] = None
    last_dbe_total: int = 0
    last_row_remap_available: Optional[int] = None


class FleetHealthTracker:
    """Maintains per-GPU sliding windows and computes health signals.

    Usage:
        tracker = FleetHealthTracker(window_seconds=300)
        tracker.observe(gpu_index=0, xid=None, sbe_total=12, dbe_total=0,
                        temperature=72, row_remap_avail=128)
        metrics = tracker.compute(gpu_index=0, gpu_uuid="...", gpu_model="...")
    """

    def __init__(self, window_seconds: float = 300.0):
        self._window = window_seconds
        self._gpus: Dict[int, _GPUWindow] = {}

    def _get(self, gpu_index: int) -> _GPUWindow:
        if gpu_index not in self._gpus:
            self._gpus[gpu_index] = _GPUWindow()
        return self._gpus[gpu_index]

    def _trim(self, buf: Deque[_Observation], now: float) -> None:
        while buf and (now - buf[0][0]) > self._window:
            buf.popleft()

    def observe(
        self,
        gpu_index: int,
        *,
        xid: Optional[int],
        sbe_total: Optional[int],
        dbe_total: Optional[int],
        temperature: Optional[float],
        row_remap_avail: Optional[int],
    ) -> None:
        """Record a new observation for the given GPU."""
        now = time.time()
        w = self._get(gpu_index)

        # XID — record the error code if it changed
        if xid is not None and xid != 0:
            if xid != w.last_xid:
                w.xid_events.append((now, float(xid)))
                w.last_xid = xid
        self._trim(w.xid_events, now)

        # SBE cumulative counter — track increments
        if sbe_total is not None:
            w.sbe_counts.append((now, float(sbe_total)))
            self._trim(w.sbe_counts, now)

        # DBE total
        if dbe_total is not None:
            w.last_dbe_total = dbe_total

        # Temperature
        if temperature is not None:
            w.temperatures.append((now, float(temperature)))
            self._trim(w.temperatures, now)

        # Row remap
        if row_remap_avail is not None:
            w.last_row_remap_available = row_remap_avail

    def compute(
        self,
        gpu_index: int,
        gpu_uuid: Optional[str],
        gpu_model: Optional[str],
        pcie_gen_current: Optional[int],
        pcie_gen_max: Optional[int],
        pcie_width_current: Optional[int],
        pcie_width_max: Optional[int],
    ) -> "GPUFleetHealthMetrics":  # noqa: F821
        from l9gpu.schemas.fleet_health_metrics import GPUFleetHealthMetrics

        w = self._get(gpu_index)

        # XID error rate (events/hour over window)
        xid_rate: Optional[float] = None
        if w.xid_events:
            xid_rate = len(w.xid_events) / (self._window / 3600.0)

        # SBE rate (increments/hour over window)
        sbe_rate: Optional[float] = None
        if len(w.sbe_counts) >= 2:
            oldest_ts, oldest_val = w.sbe_counts[0]
            newest_ts, newest_val = w.sbe_counts[-1]
            elapsed_h = (newest_ts - oldest_ts) / 3600.0
            if elapsed_h > 0:
                sbe_rate = max(0.0, (newest_val - oldest_val) / elapsed_h)

        # Thermal ramp rate (°C/min over window)
        thermal_ramp: Optional[float] = None
        if len(w.temperatures) >= 2:
            oldest_ts, oldest_t = w.temperatures[0]
            newest_ts, newest_t = w.temperatures[-1]
            elapsed_min = (newest_ts - oldest_ts) / 60.0
            if elapsed_min > 0:
                thermal_ramp = (newest_t - oldest_t) / elapsed_min

        # PCIe downtraining
        pcie_downtraining: Optional[int] = None
        if pcie_gen_current is not None and pcie_gen_max is not None:
            if pcie_width_current is not None and pcie_width_max is not None:
                downgrade = (
                    pcie_gen_current < pcie_gen_max
                    or pcie_width_current < pcie_width_max
                )
            else:
                downgrade = pcie_gen_current < pcie_gen_max
            pcie_downtraining = 1 if downgrade else 0

        # Composite health score (0–100)
        score: float = 100.0
        if pcie_downtraining:
            score -= 10.0
        if sbe_rate is not None:
            score -= 20.0 * min(1.0, sbe_rate / 10.0)
        if w.last_dbe_total > 0:
            score -= 30.0
        if w.last_row_remap_available == 0:
            score -= 15.0
        if xid_rate is not None:
            score -= 15.0 * min(1.0, xid_rate / 5.0)
        if thermal_ramp is not None and thermal_ramp > 2.0:
            score -= 10.0
        score = max(0.0, score)

        return GPUFleetHealthMetrics(
            gpu_index=gpu_index,
            gpu_uuid=gpu_uuid,
            gpu_model=gpu_model,
            xid_last_error_code=w.last_xid,
            xid_error_rate=xid_rate,
            ecc_sbe_rate=sbe_rate,
            ecc_dbe_total=w.last_dbe_total if w.last_dbe_total > 0 else None,
            row_remap_available=w.last_row_remap_available,
            pcie_link_gen_current=pcie_gen_current,
            pcie_link_width_current=pcie_width_current,
            pcie_link_downtraining=pcie_downtraining,
            thermal_ramp_rate=thermal_ramp,
            health_score=score,
        )
