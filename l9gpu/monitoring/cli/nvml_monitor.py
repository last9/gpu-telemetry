#!/usr/bin/env python3
# Copyright (c) Meta Platforms, Inc. and affiliates.
# Copyright (c) Last9, Inc.
"""Computes GPU metrics averaged over a window and publish metrics."""

import itertools
import json
import logging
import os
import socket
from copy import copy
from dataclasses import asdict, dataclass, field
from typing import (
    Callable,
    Collection,
    Dict,
    Iterable,
    List,
    Literal,
    Mapping,
    Optional,
    Protocol,
    runtime_checkable,
    Tuple,
)

import psutil
import click
from l9gpu.exporters import registry
from l9gpu.monitoring.accumulate import Accumulator
from l9gpu.monitoring.click import (
    click_default_cmd,
    cluster_option,
    DynamicEpilogCommand,
    EpilogFormatter,
    get_docs_for_references,
    get_docs_for_registry,
    heterogeneous_cluster_v1_option,
    interval_option,
    log_folder_option,
    log_level_option,
    once_option,
    sink_option,
    sink_opts_option,
    stdout_option,
)
from l9gpu.monitoring.clock import Clock, ClockImpl
from l9gpu.monitoring.dataclass_utils import max_fields
from l9gpu.monitoring.device_telemetry_client import (
    DeviceTelemetryClient,
    DeviceTelemetryException,
    GPUDevice,
)
from l9gpu.monitoring.device_telemetry_nvml import NVMLDeviceTelemetryClient
from l9gpu.monitoring.k8s_gpu_map import get_gpu_k8s_mapping
from l9gpu.monitoring.sink.protocol import DataType, SinkAdditionalParams, SinkImpl
from l9gpu.monitoring.sink.utils import Factory, HasRegistry
from l9gpu.monitoring.utils import error

from l9gpu.monitoring.utils.monitor import init_logger
from l9gpu.monitoring.utils.shell import get_command_output
from l9gpu.schemas.device_metrics import DeviceMetrics, DevicePlusJobMetrics
from l9gpu.schemas.host_metrics import HostMetrics
from l9gpu.schemas.indexed_device_metrics import IndexedDeviceMetrics
from l9gpu.schemas.job_info import JobInfo
from l9gpu.schemas.log import Log
from omegaconf import OmegaConf as oc
from typeguard import typechecked

LOGGER_NAME = "nvml_monitor"

log_error = error.log_error(logger_name=LOGGER_NAME)
logger: logging.Logger  # initialization in main()


def get_device_metrics_basic(handle: GPUDevice) -> DeviceMetrics:
    """Retrieve the device metrics."""
    metrics = DeviceMetrics(mem_used_percent=-1)

    # GPU architecture (hopper, ampere, blackwell, etc.)
    metrics.gpu_architecture = log_error(handle.get_architecture)()

    utilization = log_error(handle.get_utilization_rates)()
    if utilization is not None:
        metrics.mem_util = utilization.memory / 100.0
        metrics.gpu_util = utilization.gpu / 100.0

    memory_info = log_error(handle.get_memory_info)()
    if memory_info is not None:
        memory_total = memory_info.total / (1024 * 1024)
        memory_used = memory_info.used / (1024 * 1024)
        if memory_total > 0:
            metrics.mem_used_percent = int(memory_used / memory_total * 100)
        # Gap 1 — absolute VRAM bytes
        metrics.mem_used_bytes = memory_info.used
        metrics.mem_total_bytes = memory_info.total
        metrics.mem_free_bytes = memory_info.free
        # Phase 17: Grace-Hopper / Blackwell unified memory detection.
        # On GH200/GB200, discrete VRAM total may be 0 while unified pool is non-zero.
        # When total=0 but used>0, or when architecture name contains "grace",
        # populate unified memory fields as the primary memory metric.
        if memory_info.total == 0 and memory_info.used > 0:
            metrics.mem_unified_used_bytes = memory_info.used
            metrics.mem_unified_total_bytes = memory_info.used + memory_info.free

    metrics.temperature = log_error(handle.get_temperature)()

    power_draw = log_error(handle.get_power_usage)()
    power_limit = log_error(handle.get_enforced_power_limit)()
    if power_draw is not None:
        metrics.power_draw = power_draw
        if power_limit is not None:
            metrics.power_used_percent = power_draw / power_limit

    @log_error
    def get_retired_pages_count(source: Callable[[], Iterable[int]]) -> int:
        try:
            return len(list(source()))
        except DeviceTelemetryException:
            return 0

    metrics.retired_pages_count_single_bit = get_retired_pages_count(
        handle.get_retired_pages_multiple_single_bit_ecc_errors
    )
    metrics.retired_pages_count_double_bit = get_retired_pages_count(
        handle.get_retired_pages_double_bit_ecc_error
    )

    # Gap 2 — GPU clock frequencies (MHz)
    clock = log_error(handle.get_clock_freq)()
    if clock is not None:
        metrics.clock_graphics_mhz = clock.graphics_freq
        metrics.clock_memory_mhz = clock.memory_freq

    # Gap 3 — NVLink aggregate bandwidth (None on single-GPU / non-NVLink nodes)
    nvlink = log_error(handle.get_nvlink_throughput)()
    if nvlink is not None:
        metrics.nvlink_tx_bandwidth, metrics.nvlink_rx_bandwidth = nvlink

    # Gap 4 — ECC volatile errors (current session; reset on driver restart)
    metrics.ecc_errors_volatile_correctable = log_error(
        handle.get_ecc_corrected_volatile_total
    )()
    metrics.ecc_errors_volatile_uncorrectable = log_error(
        handle.get_ecc_uncorrected_volatile_total
    )()

    # Gap 5 — Clock throttle reasons bitmask (why clock is throttled)
    metrics.throttle_reason = log_error(handle.get_throttle_reasons)()

    # Gap 6 — GPU P-state (0=full compute, 8=idle)
    metrics.power_state = log_error(handle.get_power_state)()

    # Gap 7 — PCIe throughput (bytes/s)
    pcie = log_error(handle.get_pcie_throughput)()
    if pcie is not None:
        metrics.pcie_rx_bytes, metrics.pcie_tx_bytes = pcie

    # Gap 8 — Fan speed (0–100%)
    fan_speed = log_error(handle.get_fan_speed)()
    metrics.fan_speed_percent = fan_speed / 100.0 if fan_speed is not None else None

    # Gap 9 — Encode / decode engine utilization
    enc_dec = log_error(handle.get_encoder_decoder_util)()
    if enc_dec is not None:
        enc, dec = enc_dec
        metrics.enc_util = enc / 100.0
        metrics.dec_util = dec / 100.0

    # Gap 10 — XID error count
    metrics.xid_errors = log_error(handle.get_xid_errors)()

    # Gap 11 — PCIe replay counter
    metrics.pcie_replay_count = log_error(handle.get_pcie_replay_count)()

    # Gap 12 — Cumulative energy consumption (mJ)
    metrics.total_energy_mj = log_error(handle.get_total_energy_consumption)()

    # Gap 13 — Named throttle reason booleans (expanded from bitmask)
    if metrics.throttle_reason is not None:
        _THROTTLE_SW_POWER_CAP = 0x0000000000000004
        _THROTTLE_HW_THERMAL = 0x0000000000000040
        _THROTTLE_SW_THERMAL = 0x0000000000000080
        _THROTTLE_SYNC_BOOST = 0x0000000000000008
        bitmask = metrics.throttle_reason
        metrics.throttle_power_software = int(bool(bitmask & _THROTTLE_SW_POWER_CAP))
        metrics.throttle_temp_hardware = int(bool(bitmask & _THROTTLE_HW_THERMAL))
        metrics.throttle_temp_software = int(bool(bitmask & _THROTTLE_SW_THERMAL))
        metrics.throttle_syncboost = int(bool(bitmask & _THROTTLE_SYNC_BOOST))

    return metrics


def read_environ_from_proc(
    process_id: int,
    *,
    run_cmd: Callable[[List[str]], str] = get_command_output,
) -> Dict[str, str]:
    cmd = ["sudo", "cat", f"/proc/{process_id}/environ"]
    env_vars_raw = run_cmd(cmd).split("\x00")
    return dict(v.split("=", maxsplit=1) for v in env_vars_raw if v != "")


ProcessId = int
Env = Mapping[str, str]
EnvReader = Callable[[ProcessId], Env]


@log_error
def retrieve_job_on_gpu(
    handle: GPUDevice,
    *,
    env_reader: EnvReader = read_environ_from_proc,
) -> Optional[JobInfo]:
    """Retrieve the SLURM Job info for the job running on the GPU."""
    processes = log_error(handle.get_compute_processes)()
    if processes is None or len(processes) == 0:
        return None

    env = env_reader(processes[0].pid)
    return JobInfo.from_env(env)


def get_ram_utilization() -> float:
    """Show the RAM utilization for the host."""
    mem = psutil.virtual_memory()
    return mem.used / mem.total


def compute_host_level_metrics(
    metrics: Iterable[DeviceMetrics],
    get_ram_utilization: Callable[[], float],
) -> HostMetrics:
    gpu_utils = list(filter(None, (metric.gpu_util for metric in metrics)))
    max_gpu_util = max(gpu_utils, default=0)
    min_gpu_util = min(gpu_utils, default=0)
    avg_gpu_util = sum(gpu_utils) / len(gpu_utils) if len(gpu_utils) > 0 else 0.0

    ram_util = get_ram_utilization()

    host_level_metrics = HostMetrics(
        max_gpu_util=max_gpu_util,
        min_gpu_util=min_gpu_util,
        avg_gpu_util=avg_gpu_util,
        ram_util=ram_util,
    )

    return host_level_metrics


def log_setup(
    log_folder: str,
    hostname: str,
    device_count: int,
    log_stdout: bool,
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
) -> Tuple[logging.Logger, logging.Handler, List[logging.Formatter]]:
    logger, handler = init_logger(
        logger_name=LOGGER_NAME,
        log_dir=os.path.join(log_folder, LOGGER_NAME + "_logs"),
        log_name=hostname + ".log",
        log_formatter=logging.Formatter("[%(asctime)s] - [General] - %(message)s"),
        log_stdout=log_stdout,
        log_level=getattr(logging, log_level),
    )

    # Create GPU Specific formatters for the logger
    gpu_specific_formatter = [
        logging.Formatter("[%(asctime)s] - [GPU# {}] - %(message)s".format(idx))
        for idx in range(device_count)
    ]

    return logger, handler, gpu_specific_formatter


@runtime_checkable
class CliObject(EpilogFormatter, HasRegistry[SinkImpl], Protocol):
    def get_device_telemetry(self) -> DeviceTelemetryClient: ...

    @property
    def clock(self) -> Clock: ...

    def read_env(self, process_id: int) -> Env: ...

    def get_ram_utilization(self) -> float: ...

    def get_hostname(self) -> str: ...

    def looptimes(self, once: bool) -> Iterable[int]: ...


@dataclass
class CliObjectImpl:
    registry: Mapping[str, Factory[SinkImpl]] = field(default_factory=lambda: registry)
    clock: Clock = field(default_factory=ClockImpl)

    def get_device_telemetry(self) -> DeviceTelemetryClient:
        return NVMLDeviceTelemetryClient()

    def read_env(self, process_id: int) -> Env:
        return read_environ_from_proc(process_id)

    def get_ram_utilization(self) -> float:
        return get_ram_utilization()

    def get_hostname(self) -> str:
        return socket.gethostname().replace(".maas", "")

    def format_epilog(self) -> str:
        return get_docs_for_registry(self.registry) + get_docs_for_references(
            [
                "https://omegaconf.readthedocs.io/en/2.2_branch/usage.html#from-a-dot-list",
            ]
        )

    def looptimes(self, once: bool) -> Iterable[int]:
        if once:
            return range(1)
        return itertools.count(0)


class CustomCommand(
    DynamicEpilogCommand[CliObject],
    # SAFETY: CliObject is runtime_checkable
    obj_cls=CliObject,  # type: ignore[type-abstract]
):
    pass


# construct at module-scope because printing sink documentation relies on the object
_default_obj: CliObject = CliObjectImpl()


@click_default_cmd(cls=CustomCommand, context_settings={"obj": _default_obj})
@cluster_option
@sink_option
@sink_opts_option
@log_level_option
@log_folder_option
@stdout_option
@heterogeneous_cluster_v1_option
@click.option(
    "--push-interval",
    type=click.IntRange(min=1),
    default=60,
    help="The interval in seconds to push metrics.",
)
@click.option(
    "--collect-interval",
    type=click.IntRange(min=1),
    default=10,
    help="The interval in seconds to collect telemetry data.",
)
@interval_option(default=90)
@click.option(
    "--stdout",
    is_flag=True,
    help="Whether to display metric information to stdout.",
)
@click.option(
    "--vendor",
    type=str,
    default="nvidia",
    show_default=True,
    help="GPU vendor name reported in metric resource attributes.",
)
@once_option
@click.pass_obj
@typechecked
def main(
    obj: CliObject,
    cluster: Optional[str],
    sink: str,
    sink_opts: Collection[str],
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    log_folder: str,
    heterogeneous_cluster_v1: bool,
    push_interval: int,
    collect_interval: int,
    stdout: bool,
    interval: int,
    vendor: str,
    once: bool,
) -> None:
    """Script for reading gpu metrics on the node."""
    global logger

    device_telemetry = obj.get_device_telemetry()

    device_count = device_telemetry.get_device_count()

    hostname = obj.get_hostname()

    logger, log_handler, gpu_specific_formatter = log_setup(
        log_folder, hostname, device_count, stdout, log_level
    )

    # Inject GPU vendor, host.name, and (optionally) k8s.cluster.name as resource attributes
    # for BOTH the metric and log signals so Last9 can correlate across them.
    base_resource = [
        f"gpu.vendor={vendor}",
        f"host.name={hostname}",
    ]
    if cluster:
        base_resource.append(f"k8s.cluster.name={cluster}")

    augmented_sink_opts = list(sink_opts)
    for attr in base_resource:
        augmented_sink_opts.append(f"metric_resource_attributes.{attr}")
        augmented_sink_opts.append(f"log_resource_attributes.{attr}")
    try:
        sink_impl = obj.registry[sink](**oc.from_dotlist(augmented_sink_opts))
    except ValueError as e:
        raise click.UsageError(str(e))

    # Fetch stable per-device identity attributes once (uuid/model don't change at runtime)
    gpu_uuid_by_index: Dict[int, Optional[str]] = {}
    gpu_model_by_index: Dict[int, Optional[str]] = {}
    for device_index in range(device_count):
        handle = log_error(device_telemetry.get_device_by_index)(device_index)
        if handle is not None:
            gpu_uuid_by_index[device_index] = log_error(handle.get_uuid)()
            gpu_model_by_index[device_index] = log_error(handle.get_name)()
        else:
            gpu_uuid_by_index[device_index] = None
            gpu_model_by_index[device_index] = None

    for _ in obj.looptimes(once):
        run_st_time = obj.clock.monotonic()

        job_per_device_collection: Dict[int, JobInfo] = {
            gpu: JobInfo() for gpu in range(device_count)
        }
        accumulators = [
            Accumulator[DeviceMetrics](max_fields(DeviceMetrics))
            for _ in range(device_count)
        ]

        while obj.clock.monotonic() - run_st_time < push_interval:
            for device_index, accumulator in enumerate(accumulators):
                log_handler.setFormatter(gpu_specific_formatter[device_index])

                handle = log_error(device_telemetry.get_device_by_index)(device_index)
                if handle is None:
                    continue

                accumulator.tell(get_device_metrics_basic(handle))

                maybe_job_info = retrieve_job_on_gpu(
                    handle,
                    env_reader=obj.read_env,
                )
                if maybe_job_info is not None:
                    # Keep track of last seen job on this device (-1 if no job on device)
                    job_per_device_collection[device_index] = copy(maybe_job_info)

            obj.clock.sleep(collect_interval)

        # use the same log time for each device
        log_time = obj.clock.unixtime()
        indexed_device_metrics: List[IndexedDeviceMetrics] = []

        for index, metrics in enumerate(a.ask() for a in accumulators):
            indexed_device_metrics.append(
                IndexedDeviceMetrics(
                    gpu_index=index,
                    gpu_uuid=gpu_uuid_by_index.get(index),
                    gpu_model=gpu_model_by_index.get(index),
                    **asdict(metrics),
                )
            )

            device_plus_job_metrics = DevicePlusJobMetrics(
                gpu_id=index,
                hostname=hostname,
                **asdict(metrics),
                **asdict(job_per_device_collection[index]),
            )

            sink_impl.write(
                Log(ts=log_time, message=[device_plus_job_metrics]),
                additional_params=SinkAdditionalParams(data_type=DataType.LOG),
            )
            logger.debug(json.dumps(asdict(device_plus_job_metrics), sort_keys=True))

        host_level_metrics = compute_host_level_metrics(
            (a.ask() for a in accumulators), obj.get_ram_utilization
        )
        logger.debug(json.dumps(asdict(host_level_metrics), sort_keys=True))

        gpu_k8s_labels: Dict[int, Dict[str, str]] = {}
        node_name = os.getenv("MY_NODE_NAME")
        if os.getenv("KUBERNETES_SERVICE_HOST") and node_name:
            gpu_k8s_labels = get_gpu_k8s_mapping(node_name)

        sink_impl.write(
            Log(
                ts=log_time,
                message=indexed_device_metrics + [host_level_metrics],
            ),
            additional_params=SinkAdditionalParams(
                data_type=DataType.METRIC,
                gpu_k8s_labels=gpu_k8s_labels,
            ),
        )

        # re run every interval seconds
        obj.clock.sleep(max(0, interval - (obj.clock.monotonic() - run_st_time)))

    if hasattr(sink_impl, "shutdown"):
        sink_impl.shutdown()
