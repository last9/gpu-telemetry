# Copyright (c) Last9, Inc.
"""AMD GPU telemetry client using amdsmi."""

from typing import Callable, Dict, Iterable, List, Optional, TypeVar

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


def amdsmi_exception_handler(func: Callable[P, R]) -> Callable[P, R]:
    def inner_function(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return func(*args, **kwargs)
        except Exception as e:
            # amdsmi raises AmdSmiException or subclasses thereof
            raise DeviceTelemetryException(str(e)) from e

    return inner_function


class AMDGPUDevice:
    """Wraps an amdsmi processor handle and implements the GPUDevice protocol."""

    def __init__(self, handle: object, index: int) -> None:
        self.handle = handle
        self.index = index

    @amdsmi_exception_handler
    def get_compute_processes(self) -> List[ProcessInfo]:
        import amdsmi

        procs = amdsmi.amdsmi_get_gpu_compute_process_info(self.handle)
        return [ProcessInfo(pid=p["pid"], usedGpuMemory=p.get("mem", 0)) for p in procs]

    @amdsmi_exception_handler
    def get_retired_pages_double_bit_ecc_error(self) -> Iterable[int]:
        # AMD tracks ECC via error counts rather than page retirement lists;
        # return an empty iterable as the protocol requires
        return []

    @amdsmi_exception_handler
    def get_retired_pages_multiple_single_bit_ecc_errors(self) -> Iterable[int]:
        return []

    @amdsmi_exception_handler
    def get_retired_pages_pending_status(self) -> int:
        import amdsmi

        info = amdsmi.amdsmi_get_gpu_ras_feature_info(self.handle)
        return 1 if info.get("ecc_enabled", False) else 0

    @amdsmi_exception_handler
    def get_remapped_rows(self) -> RemappedRowInfo:
        # AMD does not expose remapped row counts; return zeroed struct
        return RemappedRowInfo(
            correctable=0,
            uncorrectable=0,
            is_pending=0,
            failure_occurred=0,
        )

    @amdsmi_exception_handler
    def get_ecc_uncorrected_volatile_total(self) -> int:
        import amdsmi

        try:
            counts = amdsmi.amdsmi_get_gpu_ecc_count(
                self.handle, amdsmi.AmdSmiGpuBlock.ANY
            )
            return counts.get("uncorrectable", 0)
        except Exception:
            return 0

    @amdsmi_exception_handler
    def get_ecc_corrected_volatile_total(self) -> int:
        import amdsmi

        try:
            counts = amdsmi.amdsmi_get_gpu_ecc_count(
                self.handle, amdsmi.AmdSmiGpuBlock.ANY
            )
            return counts.get("correctable", 0)
        except Exception:
            return 0

    @amdsmi_exception_handler
    def get_enforced_power_limit(self) -> Optional[int]:
        import amdsmi

        info = amdsmi.amdsmi_get_power_info(self.handle)
        limit_mw = info.get("power_limit", None)
        return int(limit_mw) if limit_mw is not None else None

    @amdsmi_exception_handler
    def get_power_usage(self) -> Optional[int]:
        import amdsmi

        info = amdsmi.amdsmi_get_power_info(self.handle)
        power_mw = info.get(
            "average_socket_power", info.get("current_socket_power", None)
        )
        return int(power_mw) if power_mw is not None else None

    @amdsmi_exception_handler
    def get_temperature(self) -> int:
        import amdsmi

        temp = amdsmi.amdsmi_get_temp_metric(
            self.handle,
            amdsmi.AmdSmiTemperatureType.EDGE,
            amdsmi.AmdSmiTemperatureMetric.CURRENT,
        )
        return int(temp)

    @amdsmi_exception_handler
    def get_memory_info(self) -> GPUMemory:
        import amdsmi

        vram_total = amdsmi.amdsmi_get_gpu_memory_total(
            self.handle, amdsmi.AmdSmiMemoryType.VRAM
        )
        vram_used = amdsmi.amdsmi_get_gpu_memory_usage(
            self.handle, amdsmi.AmdSmiMemoryType.VRAM
        )
        vram_free = vram_total - vram_used
        return GPUMemory(total=vram_total, free=vram_free, used=vram_used)

    @amdsmi_exception_handler
    def get_utilization_rates(self) -> GPUUtilization:
        import amdsmi

        activity = amdsmi.amdsmi_get_gpu_activity(self.handle)
        gpu_pct = activity.get("gfx_activity", 0)
        mem_pct = activity.get("umc_activity", 0)
        return GPUUtilization(gpu=int(gpu_pct), memory=int(mem_pct))

    @amdsmi_exception_handler
    def get_clock_freq(self) -> ApplicationClockInfo:
        import amdsmi

        try:
            gfx = amdsmi.amdsmi_get_gpu_metrics_info(self.handle)
            graphics_freq = gfx.get("current_gfxclk", 0)
            memory_freq = gfx.get("current_uclk", 0)
        except Exception:
            graphics_freq = 0
            memory_freq = 0
        return ApplicationClockInfo(
            graphics_freq=graphics_freq, memory_freq=memory_freq
        )

    @amdsmi_exception_handler
    def get_vbios_version(self) -> str:
        import amdsmi

        info = amdsmi.amdsmi_get_gpu_vbios_info(self.handle)
        return info.get("version", "unknown")

    def get_xgmi_link_bandwidth(self) -> Optional[List[int]]:
        """Return per-link XGMI bandwidth in bytes/sec (8 links on MI300X)."""
        try:
            import amdsmi

            info = amdsmi.amdsmi_get_xgmi_info(self.handle)
            bw = info.get("xgmi_0_data_out", None)
            if bw is None:
                return None
            # Collect all available link bandwidths
            links = []
            for i in range(8):
                key = f"xgmi_{i}_data_out"
                val = info.get(key)
                if val is not None:
                    links.append(int(val))
            return links if links else None
        except Exception:
            return None

    def get_ecc_per_block(self) -> Optional[Dict[str, int]]:
        """Return per-block ECC correctable error counts."""
        try:
            import amdsmi

            result: Dict[str, int] = {}
            for block in amdsmi.AmdSmiGpuBlock:
                try:
                    counts = amdsmi.amdsmi_get_gpu_ecc_count(self.handle, block)
                    result[block.name] = counts.get("correctable", 0)
                except Exception:
                    pass
            return result if result else None
        except Exception:
            return None

    def get_junction_temperature(self) -> Optional[int]:
        """Return junction (hotspot) temperature in Celsius."""
        try:
            import amdsmi

            temp = amdsmi.amdsmi_get_temp_metric(
                self.handle,
                amdsmi.AmdSmiTemperatureType.JUNCTION,
                amdsmi.AmdSmiTemperatureMetric.CURRENT,
            )
            return int(temp)
        except Exception:
            return None

    def get_hbm_temperature(self) -> Optional[int]:
        """Return HBM temperature in Celsius."""
        try:
            import amdsmi

            temp = amdsmi.amdsmi_get_temp_metric(
                self.handle,
                amdsmi.AmdSmiTemperatureType.VRAM,
                amdsmi.AmdSmiTemperatureMetric.CURRENT,
            )
            return int(temp)
        except Exception:
            return None


class AMDDeviceTelemetryClient:
    """Discovers and wraps AMD GPU devices via amdsmi."""

    @amdsmi_exception_handler
    def __init__(self) -> None:
        import amdsmi

        amdsmi.amdsmi_init()
        self._handles = amdsmi.amdsmi_get_processor_handles()

    @amdsmi_exception_handler
    def get_device_count(self) -> int:
        return len(self._handles)

    @amdsmi_exception_handler
    def get_device_by_index(self, index: int) -> AMDGPUDevice:
        return AMDGPUDevice(self._handles[index], index)
