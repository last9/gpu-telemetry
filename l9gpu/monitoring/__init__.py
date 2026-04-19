# Copyright (c) Meta Platforms, Inc. and affiliates.
# Copyright (c) Last9, Inc.
import logging
import os

if "L9GPU_DEBUG" in os.environ:
    logging.basicConfig(level=logging.DEBUG)
