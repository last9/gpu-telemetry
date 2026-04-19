# Copyright (c) Meta Platforms, Inc. and affiliates.
# Copyright (c) Last9, Inc.
import pytest


def pytest_configure(config: "pytest.Config") -> None:
    config.addinivalue_line("markers", "slow: the test takes some time to run")
