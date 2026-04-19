# Copyright (c) Last9, Inc.
"""Unit tests for GPU fleet health monitoring."""

import time
from l9gpu.monitoring.fleet_health import FleetHealthTracker


def test_healthy_gpu_scores_100():
    tracker = FleetHealthTracker(window_seconds=60.0)
    tracker.observe(
        0, xid=None, sbe_total=0, dbe_total=0, temperature=65.0, row_remap_avail=128
    )

    m = tracker.compute(
        0,
        "uuid-0",
        "H100",
        pcie_gen_current=5,
        pcie_gen_max=5,
        pcie_width_current=16,
        pcie_width_max=16,
    )
    assert m.health_score == 100.0
    assert m.pcie_link_downtraining == 0
    assert m.ecc_dbe_total is None  # 0 DBE → None


def test_pcie_downtraining_reduces_score():
    tracker = FleetHealthTracker(window_seconds=60.0)
    tracker.observe(
        0, xid=None, sbe_total=0, dbe_total=0, temperature=65.0, row_remap_avail=128
    )

    m = tracker.compute(
        0,
        "uuid-0",
        "H100",
        pcie_gen_current=3,
        pcie_gen_max=5,
        pcie_width_current=16,
        pcie_width_max=16,
    )
    assert m.pcie_link_downtraining == 1
    assert m.health_score == 90.0  # 100 - 10


def test_dbe_errors_critical():
    tracker = FleetHealthTracker(window_seconds=60.0)
    tracker.observe(
        0, xid=None, sbe_total=0, dbe_total=1, temperature=65.0, row_remap_avail=128
    )

    m = tracker.compute(
        0,
        "uuid-0",
        "H100",
        pcie_gen_current=5,
        pcie_gen_max=5,
        pcie_width_current=16,
        pcie_width_max=16,
    )
    assert m.ecc_dbe_total == 1
    assert m.health_score == 70.0  # 100 - 30


def test_row_remap_exhausted():
    tracker = FleetHealthTracker(window_seconds=60.0)
    tracker.observe(
        0, xid=None, sbe_total=0, dbe_total=0, temperature=65.0, row_remap_avail=0
    )

    m = tracker.compute(
        0,
        "uuid-0",
        "H100",
        pcie_gen_current=5,
        pcie_gen_max=5,
        pcie_width_current=16,
        pcie_width_max=16,
    )
    assert m.row_remap_available == 0
    assert m.health_score == 85.0  # 100 - 15


def test_xid_event_tracked():
    tracker = FleetHealthTracker(window_seconds=60.0)
    tracker.observe(
        0, xid=79, sbe_total=0, dbe_total=0, temperature=65.0, row_remap_avail=128
    )

    m = tracker.compute(
        0,
        "uuid-0",
        "H100",
        pcie_gen_current=5,
        pcie_gen_max=5,
        pcie_width_current=16,
        pcie_width_max=16,
    )
    assert m.xid_last_error_code == 79
    assert m.xid_error_rate is not None
    assert m.xid_error_rate > 0


def test_thermal_ramp_detection():
    tracker = FleetHealthTracker(window_seconds=300.0)
    # Simulate temp rising from 60 to 80 over ~60 seconds
    tracker.observe(
        0, xid=None, sbe_total=0, dbe_total=0, temperature=60.0, row_remap_avail=128
    )
    # Simulate time passing by directly appending to the deque
    w = tracker._get(0)
    now = time.time()
    w.temperatures.clear()
    w.temperatures.append((now - 60.0, 60.0))
    w.temperatures.append((now, 80.0))

    m = tracker.compute(
        0,
        "uuid-0",
        "H100",
        pcie_gen_current=5,
        pcie_gen_max=5,
        pcie_width_current=16,
        pcie_width_max=16,
    )
    # 20°C / 1 min = 20 °C/min → way above 2.0 threshold
    assert m.thermal_ramp_rate is not None
    assert m.thermal_ramp_rate > 2.0
    assert m.health_score == 90.0  # 100 - 10 (thermal)


def test_combined_failures():
    tracker = FleetHealthTracker(window_seconds=60.0)
    tracker.observe(
        0, xid=79, sbe_total=0, dbe_total=1, temperature=65.0, row_remap_avail=0
    )

    m = tracker.compute(
        0,
        "uuid-0",
        "H100",
        pcie_gen_current=3,
        pcie_gen_max=5,
        pcie_width_current=8,
        pcie_width_max=16,
    )
    # -10 (pcie) -30 (dbe) -15 (remap) -15*min(1, xid_rate/5) = at least -55+
    assert m.health_score < 50.0
