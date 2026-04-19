# Copyright (c) Last9, Inc.
"""Intel Gaudi (Habana) GPU telemetry client using hl-smi CLI parsing.

hl-smi is the only supported telemetry interface for Gaudi 2/3.
There is no Python library equivalent to pynvml or amdsmi.

Key hl-smi commands:
  hl-smi --format=csv,noheader --query-aip=<fields>  -- per-device metrics
  hl-smi -n stats                                     -- per-port network stats

Supported --query-aip fields (Gaudi 2/3):
  index, name, serial, bus_id, driver_version,
  utilization.aip, memory.used, memory.total,
  temperature.aip, power.draw
"""

import csv
import io
import subprocess
from typing import Callable, Dict, Iterable, List, Optional

from l9gpu.monitoring.device_telemetry_client import (
    ApplicationClockInfo,
    DeviceTelemetryException,
    GPUMemory,
    GPUUtilization,
    ProcessInfo,
    RemappedRowInfo,
)

# Default hl-smi binary path.
HL_SMI_PATH = "hl-smi"

# Fields requested from hl-smi per device.
HL_SMI_QUERY_FIELDS = (
    "index,name,utilization.aip,memory.used,memory.total," "temperature.aip,power.draw"
)


def _run_command(args: List[str]) -> str:
    """Run a command and return its stdout as a string."""
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            raise DeviceTelemetryException(
                f"hl-smi exited with code {result.returncode}: {result.stderr}"
            )
        return result.stdout
    except FileNotFoundError as e:
        raise DeviceTelemetryException(
            "hl-smi not found — is the Gaudi driver installed?"
        ) from e
    except subprocess.TimeoutExpired as e:
        raise DeviceTelemetryException("hl-smi timed out") from e


def _parse_hl_smi_csv(output: str) -> List[Dict[str, str]]:
    """Parse CSV output from hl-smi --format=csv,noheader into a list of dicts."""
    reader = csv.DictReader(
        io.StringIO(output.strip()),
        fieldnames=[f.strip() for f in HL_SMI_QUERY_FIELDS.split(",")],
    )
    return [
        {k.strip(): v.strip() if v is not None else "" for k, v in row.items()}
        for row in reader
    ]


def _parse_hl_smi_network_stats(output: str) -> Dict[int, Dict[str, Dict[str, int]]]:
    """Parse hl-smi -n stats output.

    Returns a dict of device_index → {port_id → {rx_bytes, tx_bytes}}.

    Example output lines:
      AIP 0 / Port 0:  RX Bytes: 1234567890  TX Bytes: 9876543210
    """
    result: Dict[int, Dict[str, Dict[str, int]]] = {}
    for line in output.splitlines():
        line = line.strip()
        if not line or "Port" not in line:
            continue
        try:
            # Format: "AIP <dev> / Port <port>:  RX Bytes: <rx>  TX Bytes: <tx>"
            parts = line.replace(":", " ").split()
            dev_idx = int(parts[1])
            port_id = int(parts[4])
            rx_idx = parts.index("RX") + 2 if "RX" in parts else -1
            tx_idx = parts.index("TX") + 2 if "TX" in parts else -1
            rx = int(parts[rx_idx]) if rx_idx > 0 else 0
            tx = int(parts[tx_idx]) if tx_idx > 0 else 0
            if dev_idx not in result:
                result[dev_idx] = {}
            result[dev_idx][str(port_id)] = {"rx_bytes": rx, "tx_bytes": tx}
        except (ValueError, IndexError):
            continue
    return result


def _parse_hl_smi_rows(output: str) -> Dict[int, Dict[str, int]]:
    """Parse hl-smi --query-aip=rows.replaced,rows.pending output.

    Returns dict of device_index → {rows_replaced, rows_pending}.
    """
    result: Dict[int, Dict[str, int]] = {}
    rows = _parse_hl_smi_csv(output)
    for row in rows:
        try:
            idx = int(row.get("index", -1))
            result[idx] = {
                "rows_replaced": int(row.get("rows.replaced", 0) or 0),
                "rows_pending": int(row.get("rows.pending", 0) or 0),
            }
        except (ValueError, KeyError):
            continue
    return result


class GaudiGPUDevice:
    """Wraps a single row of hl-smi CSV output."""

    def __init__(
        self,
        index: int,
        row: Dict[str, str],
        network_stats: Optional[Dict[str, Dict[str, int]]] = None,
        row_data: Optional[Dict[str, int]] = None,
    ) -> None:
        self.index = index
        self._row = row
        self._network_stats = network_stats or {}
        self._row_data = row_data or {}

    def _int_field(self, key: str) -> Optional[int]:
        val = self._row.get(key, "")
        # hl-smi may return "[N/A]" or empty strings for unsupported metrics.
        if not val or val.startswith("["):
            return None
        try:
            # Strip unit suffixes like " MiB", " W", " %"
            return int(val.split()[0])
        except (ValueError, IndexError):
            return None

    def get_compute_processes(self) -> List[ProcessInfo]:
        # hl-smi does not expose per-process GPU compute info
        return []

    def get_retired_pages_double_bit_ecc_error(self) -> Iterable[int]:
        return []

    def get_retired_pages_multiple_single_bit_ecc_errors(self) -> Iterable[int]:
        return []

    def get_retired_pages_pending_status(self) -> int:
        return 1 if self._row_data.get("rows_pending", 0) > 0 else 0

    def get_remapped_rows(self) -> RemappedRowInfo:
        return RemappedRowInfo(
            correctable=self._row_data.get("rows_replaced", 0),
            uncorrectable=0,
            is_pending=1 if self._row_data.get("rows_pending", 0) > 0 else 0,
            failure_occurred=0,
        )

    def get_ecc_uncorrected_volatile_total(self) -> int:
        return 0

    def get_ecc_corrected_volatile_total(self) -> int:
        return 0

    def get_enforced_power_limit(self) -> Optional[int]:
        # hl-smi does not expose configurable power limits
        return None

    def get_power_usage(self) -> Optional[int]:
        # Note: Gaudi reports 54V rail power, NOT total system power
        return self._int_field("power.draw")

    def get_temperature(self) -> int:
        return self._int_field("temperature.aip") or 0

    def get_memory_info(self) -> GPUMemory:
        total = self._int_field("memory.total") or 0
        used = self._int_field("memory.used") or 0
        # Convert MiB → bytes to match NVML convention
        total_bytes = total * 1024 * 1024
        used_bytes = used * 1024 * 1024
        free_bytes = total_bytes - used_bytes
        return GPUMemory(total=total_bytes, free=free_bytes, used=used_bytes)

    def get_utilization_rates(self) -> GPUUtilization:
        util = self._int_field("utilization.aip") or 0
        # Gaudi does not report memory controller utilization — return None
        # so it is omitted rather than misleadingly emitted as 0.
        return GPUUtilization(gpu=util, memory=None)

    def get_clock_freq(self) -> ApplicationClockInfo:
        # hl-smi does not expose clock frequencies
        return ApplicationClockInfo(graphics_freq=0, memory_freq=0)

    def get_vbios_version(self) -> str:
        return self._row.get("driver_version", "unknown")

    def get_network_rx_bandwidth(self) -> Optional[List[int]]:
        """Return per-port RX bandwidth in bytes/sec (up to 24 ports)."""
        if not self._network_stats:
            return None
        return [
            self._network_stats[p]["rx_bytes"]
            for p in sorted(self._network_stats.keys(), key=int)
            if "rx_bytes" in self._network_stats[p]
        ]

    def get_network_tx_bandwidth(self) -> Optional[List[int]]:
        """Return per-port TX bandwidth in bytes/sec (up to 24 ports)."""
        if not self._network_stats:
            return None
        return [
            self._network_stats[p]["tx_bytes"]
            for p in sorted(self._network_stats.keys(), key=int)
            if "tx_bytes" in self._network_stats[p]
        ]

    def get_rows_replaced(self) -> Optional[int]:
        v = self._row_data.get("rows_replaced")
        return v if v is not None else None

    def get_rows_pending(self) -> Optional[int]:
        v = self._row_data.get("rows_pending")
        return v if v is not None else None


class GaudiDeviceTelemetryClient:
    """Discovers and wraps Gaudi devices by parsing hl-smi output."""

    def __init__(
        self,
        hl_smi_path: str = HL_SMI_PATH,
        run_cmd: Callable[[List[str]], str] = _run_command,
    ) -> None:
        self._hl_smi = hl_smi_path
        self._run_cmd = run_cmd
        self._rows: List[Dict[str, str]] = []
        self._network_stats: Dict[int, Dict[str, Dict[str, int]]] = {}
        self._row_data: Dict[int, Dict[str, int]] = {}
        self._refresh()

    def _refresh(self) -> None:
        """Query hl-smi and refresh cached device data."""
        # Basic per-device metrics
        output = self._run_cmd(
            [
                self._hl_smi,
                "--format=csv,noheader",
                f"--query-aip={HL_SMI_QUERY_FIELDS}",
            ]
        )
        self._rows = _parse_hl_smi_csv(output)

        # Network port statistics (best-effort)
        try:
            net_output = self._run_cmd([self._hl_smi, "-n", "stats"])
            self._network_stats = _parse_hl_smi_network_stats(net_output)
        except DeviceTelemetryException:
            self._network_stats = {}

        # Row replacement tracking (best-effort)
        try:
            rows_output = self._run_cmd(
                [
                    self._hl_smi,
                    "--format=csv,noheader",
                    "--query-aip=index,rows.replaced,rows.pending",
                ]
            )
            self._row_data = _parse_hl_smi_rows(rows_output)
        except DeviceTelemetryException:
            self._row_data = {}

    def get_device_count(self) -> int:
        return len(self._rows)

    def get_device_by_index(self, index: int) -> GaudiGPUDevice:
        if index >= len(self._rows):
            raise DeviceTelemetryException(
                f"Gaudi device index {index} out of range (found {len(self._rows)} devices)"
            )
        return GaudiGPUDevice(
            index=index,
            row=self._rows[index],
            network_stats=self._network_stats.get(index, {}),
            row_data=self._row_data.get(index, {}),
        )
