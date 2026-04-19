# Copyright (c) Last9, Inc.
"""Unit tests for the Gaudi GPU monitor using a mock GaudiDeviceTelemetryClient."""

import json
from dataclasses import dataclass, field
from itertools import cycle
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Mapping, Optional

from click.testing import CliRunner
from l9gpu.exporters.do_nothing import DoNothing

from l9gpu.monitoring.cli.gaudi_monitor import (
    CliObject,
    CliObjectImpl,
    get_device_metrics_basic,
    main,
)
from l9gpu.monitoring.clock import Clock
from l9gpu.monitoring.device_telemetry_client import (
    ApplicationClockInfo,
    DeviceTelemetryClient,
    GPUMemory,
    GPUUtilization,
    ProcessInfo,
    RemappedRowInfo,
)
from l9gpu.monitoring.sink.protocol import SinkImpl
from l9gpu.monitoring.sink.utils import Factory
from l9gpu.tests.fakes import FakeClock

# ---------------------------------------------------------------------------
# Fake Gaudi GPU device
# ---------------------------------------------------------------------------


@dataclass
class FakeGaudiGPUDevice:
    """Fake Gaudi GPU device for testing."""

    power_usage: Iterator[int]
    temp: Iterator[int]
    memory_info: Iterator[GPUMemory]
    utilization: Iterator[GPUUtilization]
    network_rx: Optional[List[int]] = None
    network_tx: Optional[List[int]] = None
    rows_replaced: Optional[int] = None
    rows_pending: Optional[int] = None
    index: int = 0

    def get_compute_processes(self) -> List[ProcessInfo]:
        return []

    def get_retired_pages_double_bit_ecc_error(self) -> Iterable[int]:
        return []

    def get_retired_pages_multiple_single_bit_ecc_errors(self) -> Iterable[int]:
        return []

    def get_retired_pages_pending_status(self) -> int:
        return 0

    def get_remapped_rows(self) -> RemappedRowInfo:
        return RemappedRowInfo(0, 0, 0, 0)

    def get_ecc_uncorrected_volatile_total(self) -> int:
        return 0

    def get_ecc_corrected_volatile_total(self) -> int:
        return 0

    def get_enforced_power_limit(self) -> Optional[int]:
        return None

    def get_power_usage(self) -> Optional[int]:
        return next(self.power_usage)

    def get_temperature(self) -> int:
        return next(self.temp)

    def get_memory_info(self) -> GPUMemory:
        return next(self.memory_info)

    def get_utilization_rates(self) -> GPUUtilization:
        return next(self.utilization)

    def get_clock_freq(self) -> ApplicationClockInfo:
        return ApplicationClockInfo(graphics_freq=0, memory_freq=0)

    def get_vbios_version(self) -> str:
        return "1.16.0"

    def get_network_rx_bandwidth(self) -> Optional[List[int]]:
        return self.network_rx

    def get_network_tx_bandwidth(self) -> Optional[List[int]]:
        return self.network_tx

    def get_rows_replaced(self) -> Optional[int]:
        return self.rows_replaced

    def get_rows_pending(self) -> Optional[int]:
        return self.rows_pending


@dataclass
class FakeGaudiTelemetryClient:
    devices: List = field(default_factory=list)

    def get_device_count(self) -> int:
        return len(self.devices)

    def get_device_by_index(self, index: int):
        return self.devices[index]


def make_fake_gaudi_device(index: int = 0) -> FakeGaudiGPUDevice:
    return FakeGaudiGPUDevice(
        power_usage=iter(cycle([200, 210])),
        temp=iter(cycle([70, 72])),
        memory_info=iter(
            cycle(
                [
                    GPUMemory(total=96 * 1024**3, free=20 * 1024**3, used=76 * 1024**3),
                ]
            )
        ),
        utilization=iter(
            cycle(
                [
                    GPUUtilization(gpu=75, memory=None),
                ]
            )
        ),
        network_rx=[500_000, 600_000, 700_000],
        network_tx=[400_000, 500_000, 600_000],
        rows_replaced=2,
        rows_pending=0,
        index=index,
    )


# ---------------------------------------------------------------------------
# Tests for get_device_metrics_basic
# ---------------------------------------------------------------------------


def test_get_device_metrics_basic() -> None:
    device = make_fake_gaudi_device()
    metrics = get_device_metrics_basic(device)

    assert metrics.gpu_util == 75
    assert metrics.mem_util is None  # Gaudi does not support mem_util
    assert metrics.temperature == 70
    assert metrics.power_draw == 200
    assert metrics.network_rx_bandwidth == [500_000, 600_000, 700_000]
    assert metrics.network_tx_bandwidth == [400_000, 500_000, 600_000]
    assert metrics.rows_replaced == 2
    assert metrics.rows_pending == 0


def test_gaudi_mem_util_is_none_not_zero() -> None:
    """METRICS.md 1.6: unsupported metrics should be omitted, not emitted as 0."""
    device = make_fake_gaudi_device()
    metrics = get_device_metrics_basic(device)
    assert metrics.mem_util is None


def test_get_device_metrics_mem_used_percent() -> None:
    device = make_fake_gaudi_device()
    metrics = get_device_metrics_basic(device)
    # 76 GiB used out of 96 GiB total
    expected = int(76 / 96 * 100)
    assert metrics.mem_used_percent == expected


# ---------------------------------------------------------------------------
# Fake CLI object for integration test
# ---------------------------------------------------------------------------


@dataclass
class FakeGaudiCliObject(CliObjectImpl):
    clock: Clock = field(default_factory=FakeClock)
    registry: Mapping[str, Factory[SinkImpl]] = field(
        default_factory=lambda: {"do_nothing": DoNothing}
    )

    def get_device_telemetry(self) -> DeviceTelemetryClient:
        return FakeGaudiTelemetryClient(
            devices=[make_fake_gaudi_device(0), make_fake_gaudi_device(1)]
        )

    def read_env(self, process_id: int) -> Dict[str, str]:
        return {}

    def get_ram_utilization(self) -> float:
        return 0.50

    def get_hostname(self) -> str:
        return "gaudi-node-01"

    def format_epilog(self) -> str:
        return ""

    def looptimes(self, once: bool) -> Iterable[int]:
        return range(1)


def test_cli(tmp_path: Path) -> None:
    runner = CliRunner(mix_stderr=False)
    fake_obj: CliObject = FakeGaudiCliObject()

    result = runner.invoke(
        main,
        [
            f"--log-folder={tmp_path}",
            "--collect-interval=1",
            "--push-interval=5",
            "--sink",
            "do_nothing",
            "--stdout",
            "--once",
            "--log-level=DEBUG",
        ],
        obj=fake_obj,
        catch_exceptions=False,
    )

    lines = result.stdout.strip().split("\n")
    # Gaudi has no job correlation, so only host metrics line is logged (no per-device LOG path)
    # Per-device: 2 lines (DEBUG for each device_plus_job) + 1 host metrics
    assert len(lines) == 3, result.stdout
    assert result.exit_code == 0

    host = json.loads(lines[2].split("- ")[2])
    assert "max_gpu_util" in host
    assert "ram_util" in host
