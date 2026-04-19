# Copyright (c) Last9, Inc.
"""A single entrypoint into various l9gpu scripts.

This file is intentionally lightweight and should not include any complex logic.
"""

import click

from l9gpu._version import __version__
from l9gpu.monitoring.cli import (
    amd_monitor,
    cost_monitor,
    dcgm_monitor,
    fleet_health_monitor,
    gaudi_monitor,
    nccl_monitor,
    nim_monitor,
    nvml_monitor,
    sacct_backfill,
    sacct_publish,
    sacct_running,
    sacct_wrapper,
    sacctmgr_qos,
    sacctmgr_user,
    scontrol,
    scontrol_config,
    sglang_monitor,
    slurm_job_monitor,
    slurm_monitor,
    sprio,
    sshare,
    storage,
    tgi_monitor,
    triton_monitor,
    vllm_monitor,
)
from l9gpu.monitoring.click import DaemonGroup, detach_option, toml_config_option


@click.group(cls=DaemonGroup, epilog=f"l9gpu Version: {__version__}")
@toml_config_option("l9gpu")
@detach_option
@click.version_option(__version__)
def main(detach: bool) -> None:
    """Last9 GPU Telemetry. A toolkit for GPU monitoring, HPC cluster telemetry and health checks."""


main.add_command(nvml_monitor.main, name="nvml_monitor")
main.add_command(amd_monitor.main, name="amd_monitor")
main.add_command(gaudi_monitor.main, name="gaudi_monitor")
main.add_command(dcgm_monitor.main, name="dcgm_monitor")
main.add_command(vllm_monitor.main, name="vllm_monitor")
main.add_command(nim_monitor.main, name="nim_monitor")
main.add_command(triton_monitor.main, name="triton_monitor")
main.add_command(fleet_health_monitor.main, name="fleet_health_monitor")
main.add_command(cost_monitor.main, name="cost_monitor")
main.add_command(nccl_monitor.main, name="nccl_monitor")
main.add_command(sglang_monitor.main, name="sglang_monitor")
main.add_command(tgi_monitor.main, name="tgi_monitor")
main.add_command(sacct_running.main, name="sacct_running")
main.add_command(sacct_publish.main, name="sacct_publish")
main.add_command(sacct_wrapper.main, name="fsacct")
main.add_command(sacctmgr_qos.main, name="sacctmgr_qos")
main.add_command(sacctmgr_user.main, name="sacctmgr_user")
main.add_command(slurm_job_monitor.main, name="slurm_job_monitor")
main.add_command(slurm_monitor.main, name="slurm_monitor")
main.add_command(sacct_backfill.main, name="sacct_backfill")
main.add_command(scontrol.main, name="scontrol")
main.add_command(scontrol_config.main, name="scontrol_config")
main.add_command(sprio.main, name="sprio")
main.add_command(sshare.main, name="sshare")
main.add_command(storage.main, name="storage")

if __name__ == "__main__":
    main()
