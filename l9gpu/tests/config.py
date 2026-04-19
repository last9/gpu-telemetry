# Copyright (c) Meta Platforms, Inc. and affiliates.
# Copyright (c) Last9, Inc.
from __future__ import annotations

from typing import Mapping

from pydantic import BaseModel


class Config(BaseModel):
    """Various runtime values to be used in testing. Use sparingly.

    DO NOT use this for clowny things like flags which expose whether the code is
    running inside of a test. Test behavior should match production behavior as much as
    possible.
    """

    @classmethod
    def from_env(cls, environ: Mapping[str, str]) -> Config:
        """Construct from environment variables.

        The convention is that all config values are prefixed with 'L9GPU_TEST_' and
        converted to uppercase, e.g. a config value 'foo' could be set with value 'bar'
        via the environment with 'L9GPU_TEST_FOO=bar'.
        """
        kwargs = {}
        for f in cls.model_fields:
            kwargs[f] = environ[f"L9GPU_TEST_{f.upper()}"]
        return cls(**kwargs)
