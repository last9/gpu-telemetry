# Copyright (c) Last9, Inc.
import shlex
import subprocess
import sys

import pytest
from typeguard import check_type

from l9gpu.health_checks.subprocess import (
    handle_subprocess_exception,
    shell_command,
    ShellCommandOut,
)


@pytest.mark.parametrize("returncode", [0, 2])
def test_shell_command_result_matches_protocol(returncode: int) -> None:
    cmd = shlex.join(
        [
            sys.executable,
            "-c",
            "import sys; print('output'); print('error', file=sys.stderr); "
            f"sys.exit({returncode})",
        ]
    )

    result = shell_command(cmd, timeout_secs=10)

    check_type(result, ShellCommandOut)
    assert result.args == cmd
    assert result.returncode == returncode
    assert set(result.stdout.splitlines()) == {"output", "error"}
    assert result.stderr is None


@pytest.mark.parametrize("cmd", ["test-command --flag", ["test-command", "--flag"]])
def test_timeout_result_matches_protocol(cmd: str | list[str]) -> None:
    result = handle_subprocess_exception(subprocess.TimeoutExpired(cmd, 10))

    check_type(result, ShellCommandOut)
    assert result.args == cmd
    assert result.returncode == 128
    assert "Error command timeout because of timeout setting." in result.stdout
    with pytest.raises(subprocess.CalledProcessError):
        result.check_returncode()


def test_unknown_exception_result_matches_protocol() -> None:
    result = handle_subprocess_exception(ValueError("unexpected failure"))

    check_type(result, ShellCommandOut)
    assert result.args == []
    assert result.returncode == 2
    assert "Unknown subprocess exception" in result.stdout
