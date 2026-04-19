# Copyright (c) Last9, Inc.
"""Unit tests for the AMD GPU monitor using a mock AMDDeviceTelemetryClient."""

import json
from dataclasses import dataclass, field
from itertools import cycle
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Mapping, Optional
from unittest.mock import MagicMock

from click.testing import CliRunner
from l9gpu.exporters.do_nothing import DoNothing

from l9gpu.monitoring.cli.amd_monitor import (
    CliObject,
    CliObjectImpl,
    get_device_metrics_basic,
    main,
    retrieve_job_on_gpu,
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
# Fake AMD GPU device
# ---------------------------------------------------------------------------


@dataclass
class FakeAMDGPUDevice:
    """Fake AMD GPU device that mirrors FakeGPUDevice for testing."""

    power_usage: Iterator[int]
    temp: Iterator[int]
    memory_info: Iterator[GPUMemory]
    utilization: Iterator[GPUUtilization]
    power_limit: int
    xgmi_bw: Optional[List[int]] = None
    ecc_blocks: Optional[Dict[str, int]] = None
    junction_temp: Optional[int] = None
    hbm_temp: Optional[int] = None
    index: int = 0

    @property
    def handle(self) -> object:
        return None

    def get_compute_processes(self) -> List[ProcessInfo]:
        return [ProcessInfo(pid=1, usedGpuMemory=100)]

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
        return self.power_limit

    def get_power_usage(self) -> Optional[int]:
        return next(self.power_usage)

    def get_temperature(self) -> int:
        return next(self.temp)

    def get_memory_info(self) -> GPUMemory:
        return next(self.memory_info)

    def get_utilization_rates(self) -> GPUUtilization:
        return next(self.utilization)

    def get_clock_freq(self) -> ApplicationClockInfo:
        return ApplicationClockInfo(graphics_freq=1500, memory_freq=1200)

    def get_vbios_version(self) -> str:
        return "113-D67301-063"

    def get_xgmi_link_bandwidth(self) -> Optional[List[int]]:
        return self.xgmi_bw

    def get_ecc_per_block(self) -> Optional[Dict[str, int]]:
        return self.ecc_blocks

    def get_junction_temperature(self) -> Optional[int]:
        return self.junction_temp

    def get_hbm_temperature(self) -> Optional[int]:
        return self.hbm_temp


@dataclass
class FakeAMDTelemetryClient:
    devices: List = field(default_factory=list)

    def get_device_count(self) -> int:
        return len(self.devices)

    def get_device_by_index(self, index: int):
        return self.devices[index]


def make_fake_device(index: int = 0) -> FakeAMDGPUDevice:
    return FakeAMDGPUDevice(
        power_limit=300_000,  # milliwatts
        power_usage=iter(cycle([250_000, 260_000])),
        temp=iter(cycle([65, 68])),
        memory_info=iter(
            cycle(
                [
                    GPUMemory(
                        total=192 * 1024**3, free=50 * 1024**3, used=142 * 1024**3
                    ),
                    GPUMemory(
                        total=192 * 1024**3, free=40 * 1024**3, used=152 * 1024**3
                    ),
                ]
            )
        ),
        utilization=iter(
            cycle(
                [
                    GPUUtilization(gpu=85, memory=70),
                    GPUUtilization(gpu=90, memory=75),
                ]
            )
        ),
        xgmi_bw=[1_000_000_000, 1_100_000_000],
        ecc_blocks={"GFX": 0, "UMC": 2},
        junction_temp=72,
        hbm_temp=55,
        index=index,
    )


# ---------------------------------------------------------------------------
# Tests for get_device_metrics_basic
# ---------------------------------------------------------------------------


def test_get_device_metrics_basic() -> None:
    device = make_fake_device()
    metrics = get_device_metrics_basic(device)

    assert metrics.gpu_util == 85
    assert metrics.mem_util == 70
    assert metrics.temperature == 65
    assert metrics.power_draw == 250_000
    assert metrics.power_used_percent == 83  # 250000/300000 * 100
    assert metrics.xgmi_link_bandwidth == [1_000_000_000, 1_100_000_000]
    assert metrics.ecc_per_block == {"GFX": 0, "UMC": 2}
    assert metrics.junction_temperature == 72
    assert metrics.hbm_temperature == 55


def test_get_device_metrics_mem_used_percent() -> None:
    device = make_fake_device()
    metrics = get_device_metrics_basic(device)
    # 142 GiB used out of 192 GiB total
    expected = int(142 / 192 * 100)
    assert metrics.mem_used_percent == expected


# ---------------------------------------------------------------------------
# Tests for retrieve_job_on_gpu
# ---------------------------------------------------------------------------


def test_retrieve_job_on_gpu_no_processes() -> None:
    class NoProcessDevice(FakeAMDGPUDevice):
        def get_compute_processes(self) -> List[ProcessInfo]:
            return []

    device = NoProcessDevice(
        power_limit=300_000,
        power_usage=iter([]),
        temp=iter([]),
        memory_info=iter([]),
        utilization=iter([]),
    )
    fake_env_reader = MagicMock()
    result = retrieve_job_on_gpu(device, env_reader=fake_env_reader)
    assert result is None
    fake_env_reader.assert_not_called()


def test_retrieve_job_on_gpu_with_process() -> None:
    device = make_fake_device()

    def fake_env_reader(pid: int) -> Dict[str, str]:
        return {
            "SLURM_JOB_ID": "9999",
            "SLURM_JOB_USER": "amduser",
            "GPU_DEVICE_ORDINAL": "0",
            "SLURM_JOB_GPUS": "0",
            "SLURM_CPUS_ON_NODE": "8",
            "SLURM_JOB_NAME": "amd_training",
            "SLURM_JOB_PARTITION": "gpu",
            "SLURM_NNODES": "1",
        }

    result = retrieve_job_on_gpu(device, env_reader=fake_env_reader)
    assert result is not None
    assert result.job_id == 9999
    assert result.job_user == "amduser"


# ---------------------------------------------------------------------------
# Fake CLI object for integration test
# ---------------------------------------------------------------------------


@dataclass
class FakeAMDCliObject(CliObjectImpl):
    clock: Clock = field(default_factory=FakeClock)
    registry: Mapping[str, Factory[SinkImpl]] = field(
        default_factory=lambda: {"do_nothing": DoNothing}
    )

    def get_device_telemetry(self) -> DeviceTelemetryClient:
        return FakeAMDTelemetryClient(
            devices=[make_fake_device(0), make_fake_device(1)]
        )

    def read_env(self, process_id: int) -> Dict[str, str]:
        return {
            "SLURM_JOB_ID": "5000",
            "SLURM_JOB_USER": "rocmuser",
            "GPU_DEVICE_ORDINAL": "0",
            "SLURM_JOB_GPUS": "0",
            "SLURM_CPUS_ON_NODE": "16",
            "SLURM_JOB_NAME": "mi300x_job",
            "SLURM_JOB_PARTITION": "amd",
            "SLURM_NNODES": "1",
        }

    def get_ram_utilization(self) -> float:
        return 0.45

    def get_hostname(self) -> str:
        return "amd-node-01"

    def format_epilog(self) -> str:
        return ""

    def looptimes(self, once: bool) -> Iterable[int]:
        return range(1)


def test_cli(tmp_path: Path) -> None:
    runner = CliRunner(mix_stderr=False)
    fake_obj: CliObject = FakeAMDCliObject()

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
    # one line per device (2 devices) + one for host metrics
    assert len(lines) == 3, result.stdout
    assert result.exit_code == 0

    device_0 = json.loads(lines[0].split("- ")[2])
    assert device_0["gpu_id"] == 0
    assert device_0["hostname"] == "amd-node-01"
    assert device_0["gpu_util"] is not None
    assert device_0["temperature"] is not None

    host = json.loads(lines[2].split("- ")[2])
    assert "max_gpu_util" in host
    assert "ram_util" in host
