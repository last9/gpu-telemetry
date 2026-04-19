# Copyright (c) Meta Platforms, Inc. and affiliates.
# Copyright (c) Last9, Inc.
from dataclasses import dataclass, field
from subprocess import CompletedProcess
from typing import Iterable, List, Optional, Tuple

import psutil

from l9gpu.monitoring.device_telemetry_client import (
    ApplicationClockInfo,
    GPUMemory,
    GPUUtilization,
    ProcessInfo,
    RemappedRowInfo,
)


class FakeGPUDevice:
    def get_compute_processes(self) -> List[ProcessInfo]:
        processes = [(1, 87), (2, 90), (3, 15)]
        return [ProcessInfo(pid, gpu_memory) for pid, gpu_memory in processes]

    def get_retired_pages_double_bit_ecc_error(self) -> Iterable[int]:
        return [1, 4, 6]

    def get_retired_pages_multiple_single_bit_ecc_errors(
        self,
    ) -> Iterable[int]:
        return [3, 4, 8]

    def get_retired_pages_pending_status(self) -> int:
        return 0

    def get_remapped_rows(self) -> RemappedRowInfo:
        return RemappedRowInfo(0, 0, 0, 0)

    def get_ecc_uncorrected_volatile_total(self) -> int:
        return 0

    def get_ecc_corrected_volatile_total(self) -> int:
        return 0

    def get_enforced_power_limit(self) -> Optional[int]:
        return 12

    def get_power_usage(self) -> Optional[int]:
        return 100

    def get_temperature(self) -> int:
        return 42

    def get_memory_info(self) -> GPUMemory:
        return GPUMemory(total=100, free=20, used=80)

    def get_utilization_rates(self) -> GPUUtilization:
        return GPUUtilization(gpu=70, memory=80)

    def get_clock_freq(self) -> ApplicationClockInfo:
        return ApplicationClockInfo(graphics_freq=1155, memory_freq=1593)

    def get_vbios_version(self) -> str:
        return "86.00.4D.00.04"

    def get_uuid(self) -> str:
        return "GPU-fake-00000000-0000-0000-0000-000000000000"

    def get_name(self) -> str:
        return "Fake GPU A100"

    def get_nvlink_throughput(self) -> Optional[Tuple[int, int]]:
        return (1_000_000, 1_200_000)  # (tx_bytes_s, rx_bytes_s)

    def get_throttle_reasons(self) -> int:
        return 0

    def get_power_state(self) -> int:
        return 0

    def get_pcie_throughput(self) -> Optional[Tuple[int, int]]:
        return (50_000_000, 30_000_000)  # (rx_bytes_s, tx_bytes_s)

    def get_fan_speed(self) -> Optional[int]:
        return 65  # percent

    def get_architecture(self) -> Optional[str]:
        return "hopper"

    def get_encoder_decoder_util(self) -> Optional[Tuple[int, int]]:
        return None

    def get_pcie_replay_count(self) -> Optional[int]:
        return None

    def get_total_energy_consumption(self) -> Optional[int]:
        return None

    def get_xid_errors(self) -> Optional[int]:
        return None


@dataclass
class FakeClock:
    __current_time: float = field(init=False, default=0.0)
    __current_unixtime: int = field(init=False, default=1668197951)

    def unixtime(self) -> int:
        return self.__current_unixtime

    def monotonic(self) -> float:
        return self.__current_time

    def sleep(self, duration_sec: float) -> None:
        self.__current_time += max(0.0, duration_sec)


@dataclass
class FakeShellCommandOut(CompletedProcess):
    args: List[str] = field(default_factory=list)
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""


@dataclass
class FakeProcess(psutil.Process):
    _gone: bool = field(init=False, default=False)
    _pid: int = field(init=False, default=8)
    _name: str = field(init=False, default="")
    _pid_reused: int = field(init=False, default=8)

    def __init__(self, pid: int = 8, name: str = ""):
        self._pid = pid
        self._name = name
        self._pid_reused = pid
