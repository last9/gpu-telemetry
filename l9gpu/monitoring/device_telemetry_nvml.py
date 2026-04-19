# Copyright (c) Meta Platforms, Inc. and affiliates.
# Copyright (c) Last9, Inc.
from typing import Callable, Iterable, List, Optional, Tuple, TypeVar

import pynvml

from l9gpu.monitoring.device_telemetry_client import (
    ApplicationClockInfo,
    DeviceTelemetryException,
    GPUMemory,
    GPUUtilization,
    ProcessInfo,
    RemappedRowInfo,
)
from typing_extensions import ParamSpec

P = ParamSpec("P")
R = TypeVar("R")


def pynvml_exception_handler(func: Callable[P, R]) -> Callable[P, R]:
    def inner_function(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return func(*args, **kwargs)
        except pynvml.NVMLError as e:
            raise DeviceTelemetryException from e

    return inner_function


class NVMLGPUDevice:
    def __init__(self, handle: pynvml.c_nvmlDevice_t):
        self.handle = handle

    @pynvml_exception_handler
    def get_compute_processes(self) -> List[ProcessInfo]:
        processes = pynvml.nvmlDeviceGetComputeRunningProcesses(self.handle)
        return [
            ProcessInfo(process.pid, process.usedGpuMemory) for process in processes
        ]

    @pynvml_exception_handler
    def get_retired_pages_double_bit_ecc_error(self) -> Iterable[int]:
        return pynvml.nvmlDeviceGetRetiredPages(
            self.handle,
            pynvml.NVML_PAGE_RETIREMENT_CAUSE_DOUBLE_BIT_ECC_ERROR,
        )

    @pynvml_exception_handler
    def get_retired_pages_multiple_single_bit_ecc_errors(
        self,
    ) -> Iterable[int]:
        return pynvml.nvmlDeviceGetRetiredPages(
            self.handle,
            pynvml.NVML_PAGE_RETIREMENT_CAUSE_MULTIPLE_SINGLE_BIT_ECC_ERRORS,
        )

    @pynvml_exception_handler
    def get_retired_pages_pending_status(self) -> int:
        return pynvml.nvmlDeviceGetRetiredPagesPendingStatus(self.handle)

    @pynvml_exception_handler
    def get_remapped_rows(self) -> RemappedRowInfo:
        remapped_rows = pynvml.nvmlDeviceGetRemappedRows(self.handle)
        return RemappedRowInfo(
            remapped_rows[0],
            remapped_rows[1],
            remapped_rows[2],
            remapped_rows[3],
        )

    @pynvml_exception_handler
    def get_ecc_uncorrected_volatile_total(self) -> int:
        return pynvml.nvmlDeviceGetTotalEccErrors(
            self.handle,
            pynvml.NVML_MEMORY_ERROR_TYPE_UNCORRECTED,
            pynvml.NVML_VOLATILE_ECC,
        )

    @pynvml_exception_handler
    def get_ecc_corrected_volatile_total(self) -> int:
        return pynvml.nvmlDeviceGetTotalEccErrors(
            self.handle,
            pynvml.NVML_MEMORY_ERROR_TYPE_CORRECTED,
            pynvml.NVML_VOLATILE_ECC,
        )

    @pynvml_exception_handler
    def get_enforced_power_limit(self) -> Optional[int]:
        return pynvml.nvmlDeviceGetEnforcedPowerLimit(self.handle)

    @pynvml_exception_handler
    def get_power_usage(self) -> Optional[int]:
        return pynvml.nvmlDeviceGetPowerUsage(self.handle)

    @pynvml_exception_handler
    def get_temperature(self) -> int:
        return pynvml.nvmlDeviceGetTemperature(self.handle, pynvml.NVML_TEMPERATURE_GPU)

    @pynvml_exception_handler
    def get_memory_info(self) -> GPUMemory:
        # Phase 17: Grace-Hopper / Blackwell unified memory support.
        # On GH200/GB200, nvmlDeviceGetMemoryInfo() may return total=0 (broken).
        # Try nvmlDeviceGetMemoryInfo_v2 (NVML >= 12.0) which handles unified pools.
        # Fall back to v1 on older drivers.
        try:
            memory_info = pynvml.nvmlDeviceGetMemoryInfo(self.handle, version=2)
        except (AttributeError, TypeError, pynvml.NVMLError):
            memory_info = pynvml.nvmlDeviceGetMemoryInfo(self.handle)
        return GPUMemory(memory_info.total, memory_info.free, memory_info.used)

    @pynvml_exception_handler
    def get_utilization_rates(self) -> GPUUtilization:
        utilization_info = pynvml.nvmlDeviceGetUtilizationRates(self.handle)
        return GPUUtilization(utilization_info.gpu, utilization_info.memory)

    @pynvml_exception_handler
    def get_vbios_version(self) -> str:
        result = pynvml.nvmlDeviceGetVbiosVersion(self.handle)
        return result.decode() if isinstance(result, bytes) else result

    @pynvml_exception_handler
    def get_uuid(self) -> str:
        result = pynvml.nvmlDeviceGetUUID(self.handle)
        return result.decode() if isinstance(result, bytes) else result

    @pynvml_exception_handler
    def get_name(self) -> str:
        result = pynvml.nvmlDeviceGetName(self.handle)
        return result.decode() if isinstance(result, bytes) else result

    # NVIDIA compute capability → architecture name mapping
    _ARCH_MAP = {
        (7, 0): "volta",
        (7, 5): "turing",
        (8, 0): "ampere",
        (8, 6): "ampere",
        (8, 7): "ampere",
        (8, 9): "ada-lovelace",
        (9, 0): "hopper",
        (10, 0): "blackwell",
        (10, 1): "blackwell",
    }

    @pynvml_exception_handler
    def get_architecture(self) -> Optional[str]:
        """Return architecture name string (e.g. 'hopper', 'ampere', 'blackwell')."""
        major, minor = pynvml.nvmlDeviceGetCudaComputeCapability(self.handle)
        arch = self._ARCH_MAP.get((major, minor))
        if arch:
            return arch
        # Fallback: major version only
        return self._ARCH_MAP.get((major, 0), f"sm_{major}{minor}")

    @pynvml_exception_handler
    def get_nvlink_throughput(self) -> Optional[Tuple[int, int]]:
        """Return (tx_bytes_per_sec, rx_bytes_per_sec). None if NVLink not present."""
        tx = pynvml.nvmlDeviceGetFieldValues(
            self.handle, [pynvml.NVML_FI_DEV_NVLINK_THROUGHPUT_DATA_TX]
        )
        rx = pynvml.nvmlDeviceGetFieldValues(
            self.handle, [pynvml.NVML_FI_DEV_NVLINK_THROUGHPUT_DATA_RX]
        )
        if tx and rx and tx[0].nvmlReturn == 0 and rx[0].nvmlReturn == 0:
            return (
                tx[0].value.ullVal * 1024,
                rx[0].value.ullVal * 1024,
            )  # KiB/s → bytes/s
        return None

    @pynvml_exception_handler
    def get_throttle_reasons(self) -> int:
        return pynvml.nvmlDeviceGetCurrentClocksThrottleReasons(self.handle)

    @pynvml_exception_handler
    def get_power_state(self) -> int:
        return pynvml.nvmlDeviceGetPowerState(self.handle)

    @pynvml_exception_handler
    def get_pcie_throughput(self) -> Optional[Tuple[int, int]]:
        """Return (rx_bytes_per_sec, tx_bytes_per_sec). Converts from KB/s to bytes/s."""
        rx = pynvml.nvmlDeviceGetPcieThroughput(
            self.handle, pynvml.NVML_PCIE_UTIL_RX_BYTES
        )
        tx = pynvml.nvmlDeviceGetPcieThroughput(
            self.handle, pynvml.NVML_PCIE_UTIL_TX_BYTES
        )
        return (rx * 1024, tx * 1024)

    @pynvml_exception_handler
    def get_fan_speed(self) -> Optional[int]:
        return pynvml.nvmlDeviceGetFanSpeed(self.handle)

    @pynvml_exception_handler
    def get_encoder_decoder_util(self) -> Optional[Tuple[int, int]]:
        """Return (encoder_util, decoder_util) as percentages 0-100."""
        enc_util, _enc_period = pynvml.nvmlDeviceGetEncoderUtilization(self.handle)
        dec_util, _dec_period = pynvml.nvmlDeviceGetDecoderUtilization(self.handle)
        return (enc_util, dec_util)

    @pynvml_exception_handler
    def get_xid_errors(self) -> Optional[int]:
        """Return the cumulative XID error count via field value query."""
        # NVML_FI_DEV_XID_ERRORS = 32
        NVML_FI_DEV_XID_ERRORS = 32
        results = pynvml.nvmlDeviceGetFieldValues(self.handle, [NVML_FI_DEV_XID_ERRORS])
        if results and results[0].nvmlReturn == 0:
            return results[0].value.ullVal
        return None

    @pynvml_exception_handler
    def get_pcie_replay_count(self) -> Optional[int]:
        """Return the cumulative PCIe replay counter."""
        return pynvml.nvmlDeviceGetPcieReplayCounter(self.handle)

    @pynvml_exception_handler
    def get_total_energy_consumption(self) -> Optional[int]:
        """Return cumulative energy consumption in millijoules."""
        return pynvml.nvmlDeviceGetTotalEnergyConsumption(self.handle)

    @pynvml_exception_handler
    def get_clock_freq(self) -> ApplicationClockInfo:
        # For the type parameter https://github.com/gpuopenanalytics/pynvml/blob/41e1657948b18008d302f5cb8af06539adc7c792/pynvml/nvml.py#L168
        NVML_CLOCK_GRAPHICS = 0
        NVML_CLOCK_MEM = 2

        graphics_freq = pynvml.nvmlDeviceGetClockInfo(self.handle, NVML_CLOCK_GRAPHICS)
        memory_freq = pynvml.nvmlDeviceGetClockInfo(self.handle, NVML_CLOCK_MEM)
        return ApplicationClockInfo(graphics_freq, memory_freq)


class NVMLDeviceTelemetryClient:
    @pynvml_exception_handler
    def __init__(self) -> None:
        pynvml.nvmlInit()

    @pynvml_exception_handler
    def get_device_count(self) -> int:
        return pynvml.nvmlDeviceGetCount()

    @pynvml_exception_handler
    def get_device_by_index(self, index: int) -> NVMLGPUDevice:
        device = pynvml.nvmlDeviceGetHandleByIndex(index)
        return NVMLGPUDevice(device)
