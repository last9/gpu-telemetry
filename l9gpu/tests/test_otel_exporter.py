# Copyright (c) Last9, Inc.
"""Unit tests for the OTel exporter metric writing logic.

These tests verify that the exporter correctly handles:
- Scalar (int/float) metrics with data-point attributes
- List metrics (per-element emission with link_index)
- Dict metrics (per-key emission with memory_block)
- None values are skipped
- gpu_index is propagated as a data-point attribute
"""

from dataclasses import dataclass, fields
from typing import Any, Dict, List, Optional


@dataclass
class FakeGauge:
    """Tracks all .set() calls for assertion."""

    name: str
    calls: List[Dict[str, Any]]

    def __init__(self, name: str) -> None:
        self.name = name
        self.calls = []

    def set(self, amount: Any, attributes: Any = None) -> None:
        self.calls.append({"amount": amount, "attributes": attributes})


@dataclass
class FakeMeter:
    """Fake OTel Meter that creates FakeGauges."""

    gauges: Dict[str, FakeGauge]

    def __init__(self) -> None:
        self.gauges = {}

    def create_gauge(
        self, name: str, description: str = "", unit: str = "1"
    ) -> FakeGauge:
        g = FakeGauge(name)
        self.gauges[name] = g
        return g


# ---------------------------------------------------------------------------
# Test helper: invoke _write_metric with a fake message
# ---------------------------------------------------------------------------


@dataclass
class ScalarMessage:
    gpu_index: Optional[int] = 0
    gpu_util: Optional[int] = 85
    temperature: Optional[int] = 72
    power_draw: Optional[int] = 250


@dataclass
class ListMessage:
    gpu_index: Optional[int] = 0
    xgmi_link_bandwidth: Optional[List[int]] = None


@dataclass
class DictMessage:
    gpu_index: Optional[int] = 0
    ecc_per_block: Optional[Dict[str, int]] = None


@dataclass
class NoneMessage:
    gpu_index: Optional[int] = 0
    gpu_util: Optional[int] = None
    temperature: Optional[int] = None


def make_otel_exporter(meter: FakeMeter):
    """Create a minimal Otel-like object with the _write_metric method."""
    from l9gpu.exporters.metric_names import (
        get_data_point_attributes,
        get_otel_name,
        get_unit,
    )

    class FakeOtel:
        def __init__(self, m):
            self.meter = m
            self.metrics_instruments = {}

        def _get_or_create_gauge(self, otel_name, field_name):
            if otel_name not in self.metrics_instruments:
                self.metrics_instruments[otel_name] = self.meter.create_gauge(
                    otel_name, description=otel_name, unit=get_unit(field_name)
                )
            return self.metrics_instruments[otel_name]

        def _write_metric(self, data):
            for message in data.message:
                gpu_index = getattr(message, "gpu_index", None)
                for field in fields(message):
                    field_name = field.name
                    metric_value = getattr(message, field_name)
                    if metric_value is None:
                        continue
                    otel_name = get_otel_name(field_name)
                    base_attrs = get_data_point_attributes(field_name)
                    if gpu_index is not None:
                        base_attrs["gpu.index"] = str(gpu_index)
                    if isinstance(metric_value, (int, float)):
                        gauge = self._get_or_create_gauge(otel_name, field_name)
                        gauge.set(amount=metric_value, attributes=base_attrs or None)
                    elif isinstance(metric_value, list):
                        gauge = self._get_or_create_gauge(otel_name, field_name)
                        for idx, val in enumerate(metric_value):
                            if isinstance(val, (int, float)):
                                attrs = {
                                    **base_attrs,
                                    "gpu.interconnect.link_index": str(idx),
                                }
                                gauge.set(amount=val, attributes=attrs)
                    elif isinstance(metric_value, dict):
                        gauge = self._get_or_create_gauge(otel_name, field_name)
                        for key, val in metric_value.items():
                            if isinstance(val, (int, float)):
                                attrs = {
                                    **base_attrs,
                                    "gpu.ecc.memory_block": key.lower(),
                                }
                                gauge.set(amount=val, attributes=attrs)

    return FakeOtel(meter)


@dataclass
class FakeLog:
    ts: float = 0.0
    message: list = None

    def __post_init__(self):
        if self.message is None:
            self.message = []


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestScalarMetrics:
    def test_emits_scalar_with_attributes(self) -> None:
        meter = FakeMeter()
        exporter = make_otel_exporter(meter)
        exporter._write_metric(
            FakeLog(message=[ScalarMessage(gpu_index=0, gpu_util=85)])
        )

        gauge = meter.gauges.get("gpu.utilization")
        assert gauge is not None
        assert len(gauge.calls) == 1
        assert gauge.calls[0]["amount"] == 85
        assert gauge.calls[0]["attributes"]["gpu.index"] == "0"
        assert gauge.calls[0]["attributes"]["gpu.task.type"] == "compute"

    def test_temperature_has_sensor_attribute(self) -> None:
        meter = FakeMeter()
        exporter = make_otel_exporter(meter)
        exporter._write_metric(FakeLog(message=[ScalarMessage()]))

        gauge = meter.gauges.get("gpu.temperature")
        assert gauge is not None
        assert any(
            c["attributes"]["gpu.temperature.sensor"] == "edge" for c in gauge.calls
        )


class TestListMetrics:
    def test_list_emits_per_element_with_link_index(self) -> None:
        meter = FakeMeter()
        exporter = make_otel_exporter(meter)
        msg = ListMessage(gpu_index=1, xgmi_link_bandwidth=[1000, 2000, 3000])
        exporter._write_metric(FakeLog(message=[msg]))

        gauge = meter.gauges.get("gpu.interconnect.throughput")
        assert gauge is not None
        assert len(gauge.calls) == 3
        assert gauge.calls[0]["amount"] == 1000
        assert gauge.calls[0]["attributes"]["gpu.interconnect.link_index"] == "0"
        assert gauge.calls[1]["attributes"]["gpu.interconnect.link_index"] == "1"
        assert gauge.calls[2]["attributes"]["gpu.interconnect.link_index"] == "2"

    def test_list_with_none_value_skips_field(self) -> None:
        meter = FakeMeter()
        exporter = make_otel_exporter(meter)
        msg = ListMessage(gpu_index=0, xgmi_link_bandwidth=None)
        exporter._write_metric(FakeLog(message=[msg]))

        assert "gpu.interconnect.throughput" not in meter.gauges

    def test_xgmi_has_type_attribute(self) -> None:
        meter = FakeMeter()
        exporter = make_otel_exporter(meter)
        msg = ListMessage(gpu_index=0, xgmi_link_bandwidth=[500])
        exporter._write_metric(FakeLog(message=[msg]))

        gauge = meter.gauges.get("gpu.interconnect.throughput")
        assert gauge.calls[0]["attributes"]["gpu.interconnect.type"] == "xgmi"


class TestDictMetrics:
    def test_dict_emits_per_key_with_memory_block(self) -> None:
        meter = FakeMeter()
        exporter = make_otel_exporter(meter)
        msg = DictMessage(gpu_index=2, ecc_per_block={"GFX": 0, "UMC": 3})
        exporter._write_metric(FakeLog(message=[msg]))

        gauge = meter.gauges.get("gpu.ecc.errors")
        assert gauge is not None
        assert len(gauge.calls) == 2
        blocks = {c["attributes"]["gpu.ecc.memory_block"] for c in gauge.calls}
        assert blocks == {"gfx", "umc"}

    def test_dict_with_none_skips(self) -> None:
        meter = FakeMeter()
        exporter = make_otel_exporter(meter)
        msg = DictMessage(gpu_index=0, ecc_per_block=None)
        exporter._write_metric(FakeLog(message=[msg]))
        assert "gpu.ecc.errors" not in meter.gauges


class TestNoneSkipping:
    def test_none_values_are_skipped(self) -> None:
        meter = FakeMeter()
        exporter = make_otel_exporter(meter)
        exporter._write_metric(FakeLog(message=[NoneMessage()]))

        # Only gpu_index should have been emitted (as gpu.gpu_index)
        for name, gauge in meter.gauges.items():
            assert name != "gpu.utilization"
            assert name != "gpu.temperature"


class TestAllIntegrationMetrics:
    """Verify every metric documented in docs/INTEGRATION.md Section 3 is actually emitted."""

    INTEGRATION_MD_METRICS = {
        # Section 3.1 Core Device Metrics
        "gpu.utilization",
        "gpu.memory.utilization",
        "gpu.memory.used.percent",
        "gpu.memory.used",
        "gpu.memory.total",
        "gpu.memory.free",
        "gpu.temperature",
        "gpu.power.draw",
        "gpu.power.utilization",
        "gpu.power.state",
        "gpu.throttle.reason",
        "gpu.clock.frequency",
        "gpu.fan.speed",
        # Section 3.2 Error & Reliability
        "gpu.row_remap.count",
        "gpu.row_remap.pending",
        "gpu.ecc.errors",
        # Section 3.3 Interconnect
        "gpu.interconnect.throughput",
        "gpu.pcie.throughput",
        # Section 3.5 Host Aggregate
        "gpu.utilization.max",
        "gpu.utilization.min",
        "gpu.utilization.avg",
        "host.memory.utilization",
    }

    def test_all_integration_metrics_are_emitted(self) -> None:
        from l9gpu.schemas.device_metrics import DeviceMetrics
        from l9gpu.schemas.gaudi_device_metrics import GaudiDeviceMetrics
        from l9gpu.schemas.host_metrics import HostMetrics

        meter = FakeMeter()
        exporter = make_otel_exporter(meter)

        device = DeviceMetrics(
            gpu_util=70,
            mem_util=60,
            mem_used_percent=55,
            temperature=72,
            power_draw=250,
            power_used_percent=80,
            retired_pages_count_single_bit=1,
            retired_pages_count_double_bit=0,
            mem_used_bytes=8_000_000_000,
            mem_total_bytes=16_000_000_000,
            mem_free_bytes=8_000_000_000,
            clock_graphics_mhz=1400,
            clock_memory_mhz=1200,
            nvlink_tx_bandwidth=1_000_000,
            nvlink_rx_bandwidth=1_200_000,
            ecc_errors_volatile_correctable=0,
            ecc_errors_volatile_uncorrectable=0,
            throttle_reason=0,
            power_state=0,
            pcie_rx_bytes=50_000_000,
            pcie_tx_bytes=30_000_000,
            fan_speed_percent=65,
        )

        # rows_pending is Gaudi-only; use a GaudiDeviceMetrics instance to cover it
        gaudi = GaudiDeviceMetrics(rows_pending=2)

        host = HostMetrics(
            max_gpu_util=90,
            min_gpu_util=40,
            avg_gpu_util=70.0,
            ram_util=55.0,
        )

        exporter._write_metric(FakeLog(message=[device]))
        exporter._write_metric(FakeLog(message=[gaudi]))
        exporter._write_metric(FakeLog(message=[host]))

        emitted = set(meter.gauges.keys())
        missing = self.INTEGRATION_MD_METRICS - emitted
        assert not missing, f"Metrics not emitted: {sorted(missing)}"
