# Copyright (c) Meta Platforms, Inc. and affiliates.
# Copyright (c) Last9, Inc.
import json
import logging
from dataclasses import asdict

from l9gpu.exporters import register

from l9gpu.monitoring.dataclass_utils import (
    flatten_dict_factory,
    remove_none_dict_factory,
)
from l9gpu.monitoring.sink.protocol import DataType, SinkAdditionalParams
from l9gpu.schemas.log import Log

logger = logging.getLogger(__name__)


@register("stdout")
class Stdout:
    """Write data to stdout."""

    def __init__(self, **kwargs):
        pass

    def _write_log(self, data: Log) -> None:
        print(
            json.dumps(
                [
                    asdict(message, dict_factory=remove_none_dict_factory)
                    for message in data.message
                ]
            )
        )

    def _write_metric(self, data: Log) -> None:
        print(
            json.dumps(
                [
                    asdict(message, dict_factory=flatten_dict_factory)
                    for message in data.message
                ]
            )
        )

    def write(
        self,
        data: Log,
        additional_params: SinkAdditionalParams,
    ) -> None:
        if additional_params.data_type:
            if additional_params.data_type is DataType.LOG:
                return self._write_log(data)
            elif additional_params.data_type is DataType.METRIC:
                return self._write_metric(data)
            else:
                logger.error(
                    f"We expected log or metrics, but got {additional_params.data_type}"
                )
        else:
            logger.error(
                f"Stdout writes requires data_type to be specified: {additional_params}"
            )
            return
