# Copyright (c) Meta Platforms, Inc. and affiliates.
# Copyright (c) Last9, Inc.
"""A single entrypoint into various health check scripts.

This file is intentionally lightweight and should not include any complex logic.
"""

from typing import List

import click
from l9gpu._version import __version__
from l9gpu.health_checks import checks
from l9gpu.health_checks.click import DEFAULT_CONFIG_PATH

from l9gpu.monitoring.click import (
    DaemonGroup,
    detach_option,
    feature_flags_config,
    toml_config_option,
)
from l9gpu.monitoring.features.gen.generated_features_healthchecksfeatures import (
    FeatureValueHealthChecksFeatures,
)


@click.group(cls=DaemonGroup, epilog=f"health_checks version: {__version__}")
@feature_flags_config(FeatureValueHealthChecksFeatures)
@toml_config_option("health_checks", default_config_path=DEFAULT_CONFIG_PATH)
@detach_option
@click.version_option(__version__)
def health_checks(detach: bool) -> None:
    """Last9 GPU Telemetry: Vendor-Agnostic GPU Monitoring for AI/HPC Clusters."""


list_of_checks: List[click.core.Command] = [
    checks.check_ssh_certs,
    checks.check_telemetry,
    checks.check_dcgmi,
    checks.check_hca,
    checks.check_nccl,
    checks.check_nvidia_smi,
    checks.check_syslogs,
    checks.check_process,
    checks.cuda,
    checks.check_storage,
    checks.check_processor,
    checks.check_ipmitool,
    checks.check_service,
    checks.check_ib,
    checks.check_authentication,
    checks.check_node,
    checks.check_pci,
    checks.check_blockdev,
    checks.check_ethlink,
    checks.check_sensors,
]

for check in list_of_checks:
    health_checks.add_command(check)

if __name__ == "__main__":
    health_checks()
