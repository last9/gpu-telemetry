# Copyright (c) Meta Platforms, Inc. and affiliates.
# Copyright (c) Last9, Inc.
from l9gpu.exporters import register
from l9gpu.monitoring.sink.protocol import SinkAdditionalParams
from l9gpu.schemas.log import Log


@register("do_nothing")
class DoNothing:
    """Placeholder Sink"""

    def __init__(self, **kwargs: object) -> None:
        # Accept (and ignore) any constructor kwargs passed by the sink
        # factory — e.g. metric_resource_attributes.* / log_resource_attributes.*
        # injected by the monitor CLIs. This sink is a no-op.
        pass

    def write(
        self,
        data: Log,
        additional_params: SinkAdditionalParams,
    ) -> None:
        pass
