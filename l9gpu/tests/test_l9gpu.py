# Copyright (c) Last9, Inc.
import pytest
from click.testing import CliRunner

from l9gpu.monitoring.cli.l9gpu import main


@pytest.mark.parametrize("command", main.commands.keys())
def test_cli(command: str) -> None:
    if command == "fsacct":
        pytest.skip(
            "fsacct --help delegates to sacct via subprocess. subprocess output is not captured by CliRunner. Furthermore, we cannot forward to the parent's stdout/stderr (i.e. via `sys.stdout` or `sys.stderr`) because neither are backed by file descriptors at test time."
        )
    runner = CliRunner()

    result = runner.invoke(main, [command, "--help"], catch_exceptions=False)

    assert result.stdout.strip() != ""
