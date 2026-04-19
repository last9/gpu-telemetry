<!-- Copyright (c) Meta Platforms, Inc. and affiliates. -->
<!--
Copyright (c) Last9, Inc.
-->
# Last9 GPU Telemetry (l9gpu)

This is the core Python CLI toolset for Last9 GPU Telemetry, providing comprehensive monitoring and health checking capabilities for High-Performance Computing (HPC) and AI/ML clusters.

## Overview

The l9gpu Python library consists of the following components:

### **Monitoring** ([`/monitoring/`](/monitoring/))
Collects cluster statistics from the [Slurm](https://slurm.schedmd.com/documentation.html) workload scheduler, and [NVIDIA Management Library (NVML)](https://developer.nvidia.com/management-library-nvml), providing visibility into job performance and resource utilization.

**Available CLI Commands** (via `l9gpu`):
- `l9gpu slurm_monitor --sink=stdout --once` - Job, node and diagnostics statistics according to `sacct`, `sinfo`, and `squeue`
- `l9gpu sacct_backfill --once new -s 'today 4pm' -e 'today 5pm' -- l9gpu sacct_publish --sink stdout` - Historical finished jobs data backfill according to `sacct`
- `l9gpu sacct_running --sink=stdout --once` - Running Jobs according to `sacct`
- `l9gpu sacctmgr_qos --sink=stdout --once` - QOS information according to `sacctmgr`
- `l9gpu sacctmgr_user --sink=stdout --once` - User information according to `sacctmgr`
- `l9gpu slurm_job_monitor --sink=stdout --once` - Job queue and node state information according to `squeue` and `sinfo`
- `l9gpu scontrol --sink=stdout --once` - Slurm control plane monitoring
- `l9gpu scontrol_config --sink=stdout --once` - Slurm configuration file monitoring
- `l9gpu storage --help` - Storage system monitoring
- `l9gpu nvml_monitor --sink=stdout --once` - GPU telemetry collection

You can see the full list of monitoring components with:
```shell
l9gpu --help
```

### **Health Checks** ([`/health_checks/`](/health_checks/))
Verifies the proper functioning of hardware, software, network, storage, and services throughout the job lifecycle. Includes 20+ specialized health checks.

You can check the full list of health checks [here](health_checks/README.md#check-contents). You can also see the full list of health checks with:
```shell
health_checks --help
```

## Installation

### Requirements
- **Python 3.10+** (currently tested on 3.10, later versions should work)
- **NVIDIA GPUs** (for GPU monitoring features)
- **Slurm** (for job scheduler integration)

### Install from Git
```shell
# Latest main
pip install --upgrade git+ssh://git@github.com:last9/gpu-telemetry.git@main

# Specific release
pip install --upgrade git+ssh://git@github.com:last9/gpu-telemetry.git@2022.9.20
```

### Development Installation
```shell
# Clone and setup development environment
git clone https://github.com/last9/gpu-telemetry
cd l9gpu

# Create conda environment
conda create -y --name py310 python==3.10
conda activate py310

# Install dependencies
pip install -r dev-requirements.txt
pip install --no-deps -e .

# Install pre-commit hooks
pre-commit install
```

## Quick Start

### Basic Monitoring
```shell
# Start monitoring with stdout output (for testing)
l9gpu slurm_monitor --sink=stdout --once

# Start continuous monitoring with file output
l9gpu slurm_monitor --sink=file --sink-opt path=/var/log/l9gpu/monitoring.json

# Monitor with OpenTelemetry export
l9gpu slurm_monitor --sink=otel --sink-opt endpoint=http://localhost:4317
```

### Health Checks
```shell
# Run GPU diagnostics
health_checks check-dcgmi diag my_cluster prolog --sink=stdout

# Check GPU status via NVML
health_checks check-nvidia-smi my_cluster prolog -c gpu_num -c running_procs --sink=stdout

# Check storage and mounts
health_checks check-storage disk-usage my_cluster prolog -v /dev/root --usage-critical-threshold=85 --sink=stdout

# Monitor system processes
health_checks check-process check-zombie my_cluster prolog --elapsed=200 --sink=stdout
```

### Configuration Files
Both monitoring and health checks support TOML configuration files to simplify parameter management:

```shell
# Using config file for monitoring
l9gpu --config=/etc/cluster_config.toml slurm_monitor

# CLI arguments override config file values
l9gpu --config=/etc/cluster_config.toml slurm_monitor --sink=stdout --once
```
Example configuration file in [`/monitoring/config/config.toml`](./monitoring/config/config.toml).

```shell
# Using config file for health checks
health_checks --config=cluster_config.toml check-dcgmi diag

# Using feature flags
health_checks --features-config=features.toml --config=cluster_config.toml check-nvidia-smi
```
Example configuration files are available in [`/health_checks/config/`](./health_checks/config/).

## Documentation

- **[Adding a New Collector](docs/adding_new_collector.md)**
- **[Health Checks Onboarding](docs/health_checks_onboarding.md)**
- **[Adding a New Exporter/Sink](docs/adding_new_exporter.md)**
- **[Adding a New Health Check](docs/health_checks_onboarding.md#how-to-write-a-new-health-check)**
- **[Contributing Guide](CONTRIBUTING.md)** - Development setup and contribution guidelines
- **[Release Process](docs/release.md)** - How releases are managed

## Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for:

- Development environment setup
- Code style and testing requirements
- Pull request process
- Dependency management

## Supported Python Versions

Python 3.10 or greater is required. Currently only 3.10 is tested, but later versions should work as well.

## License

This component is licensed under the [MIT License](LICENSE).
