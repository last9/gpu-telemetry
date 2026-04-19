# Copyright (c) Meta Platforms, Inc. and affiliates.
# Copyright (c) Last9, Inc.
from pathlib import Path
from typing import ClassVar, Optional, Protocol


class FeaturesConfig(Protocol):
    config_path: ClassVar[Optional[Path]]
