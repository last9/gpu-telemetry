# Copyright (c) Meta Platforms, Inc. and affiliates.
# Copyright (c) Last9, Inc.
from typing import Tuple

import pynvml
from l9gpu.health_checks.check_utils.pynvml_errors import handle_pynvml_error
from l9gpu.health_checks.types import ExitCode

from l9gpu.monitoring.device_telemetry_client import DeviceTelemetryException


def handle_device_telemetry_exception(
    e: DeviceTelemetryException,
) -> Tuple[ExitCode, str]:
    """Handle the different DeviceTelemetry Exceptions"""
    exc_cause = e.__cause__
    if exc_cause and isinstance(exc_cause, pynvml.NVMLError):
        return handle_pynvml_error(e)
    else:
        return (
            ExitCode.CRITICAL,
            "Unknown instance of DeviceTelemetryException",
        )
