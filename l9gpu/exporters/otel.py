# Copyright (c) Meta Platforms, Inc. and affiliates.
# Copyright (c) Last9, Inc.
import logging
import os
from dataclasses import asdict, fields
from typing import Any, cast, Dict, Optional

from l9gpu.exporters import register
from l9gpu.exporters.genai_metric_names import (
    FIELD_TO_GENAI_NAME,
    GENAI_DATA_POINT_ATTRIBUTES,
)
from l9gpu.exporters.metric_names import (
    get_data_point_attributes,
    get_otel_name,
    get_unit,
)

from l9gpu.monitoring.dataclass_utils import flatten_dict_factory
from l9gpu.monitoring.sink.protocol import DataType, SinkAdditionalParams
from l9gpu.schemas.log import Log

from omegaconf import DictConfig, OmegaConf
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.metrics import _Gauge
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor

from opentelemetry.sdk.metrics import Meter, MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

from opentelemetry.sdk.resources import (  # type: ignore[attr-defined]
    Resource,
    SERVICE_NAME,
)

from typing_extensions import Never

logger = logging.getLogger(__name__)

# Identity fields — emitted as data-point attributes (gpu.index, gpu.uuid, gpu.model),
# not as metric values. Skipped in _write_metric() to prevent spurious gauges.
_IDENTITY_FIELDS = {
    "gpu_index",
    "gpu_uuid",
    "gpu_model",  # DeviceMetrics / DcgmProfilingMetrics
    "mig_enabled",
    "mig_instance_id",  # DcgmProfilingMetrics (Phase 6)
    "rank",  # NCCLCollectiveMetrics (Phase 13)
}


def _flatten_resource_attrs(d: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
    """Flatten nested dicts to dot-separated keys for OTel Resource attributes."""
    result: Dict[str, Any] = {}
    for k, v in d.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            result.update(_flatten_resource_attrs(v, key))
        else:
            result[key] = v
    return result


def _get_otlp_headers() -> Dict[str, str]:
    """Parse OTEL_EXPORTER_OTLP_HEADERS env var into a dict.

    Format: 'key1=value1,key2=value2' or 'key1=value1' (single header).
    Handles base64 values that contain '=' by splitting on first '=' only.
    """
    raw = os.environ.get("OTEL_EXPORTER_OTLP_HEADERS", "")
    if not raw:
        return {}
    headers: Dict[str, str] = {}
    for part in raw.split(","):
        part = part.strip()
        if "=" in part:
            key, _, value = part.partition("=")
            headers[key.strip()] = value.strip()
    return headers


def otel_log_init(
    resource_attributes: Optional[DictConfig], otel_endpoint: str, otel_timeout: int
) -> LoggerProvider:
    resource_attrs_dict: Dict[str, Any] = cast(
        Dict[str, Any],
        (
            OmegaConf.to_container(resource_attributes, resolve=True)
            if resource_attributes is not None
            else {}
        ),
    )

    resource = Resource(attributes=_flatten_resource_attrs(resource_attrs_dict))

    logger_provider = LoggerProvider(resource=resource)
    exporter = OTLPLogExporter(
        endpoint=otel_endpoint,
        timeout=otel_timeout,
        headers=_get_otlp_headers(),
    )
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(exporter))
    return logger_provider


def otel_metric_init(
    resource_attributes: Optional[DictConfig], otel_endpoint: str, otel_timeout: int
) -> Meter:
    resource_attrs_dict: Dict[str, Any] = cast(
        Dict[str, Any],
        (
            OmegaConf.to_container(resource_attributes, resolve=True)
            if resource_attributes is not None
            else {}
        ),
    )

    resource = Resource(attributes=_flatten_resource_attrs(resource_attrs_dict))
    exporter = OTLPMetricExporter(
        endpoint=otel_endpoint,
        timeout=otel_timeout,
        headers=_get_otlp_headers(),
    )
    reader = PeriodicExportingMetricReader(
        exporter, export_interval_millis=60000, export_timeout_millis=5000
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
    return meter_provider.get_meter("l9gpu-meter")


def get_otel_endpoint(otel_endpoint: Optional[str]) -> str:
    if otel_endpoint is None:
        if "OTEL_EXPORTER_OTLP_ENDPOINT" not in os.environ:
            raise ValueError(
                "could not find a otel exporter otlp endpoint, you can set the environment variable OTEL_EXPORTER_OTLP_ENDPOINT."
            )
        return os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"]
    return otel_endpoint


def get_otel_timeout(otel_timeout: Optional[int]) -> int:
    if otel_timeout is None:
        if "OTEL_EXPORTER_OTLP_TIMEOUT" not in os.environ:
            raise ValueError(
                "could not find a otel exporter otlp endpoint, you can set the environment variable OTEL_EXPORTER_OTLP_TIMEOUT."
            )
        return int(os.environ["OTEL_EXPORTER_OTLP_TIMEOUT"])
    return otel_timeout


@register("otel")
class Otel:
    def __init__(
        self,
        *,
        log_resource_attributes: Optional[DictConfig] = None,
        metric_resource_attributes: Optional[DictConfig] = None,
        otel_endpoint: Optional[str] = None,
        otel_timeout: Optional[int] = None,
    ):
        endpoint = get_otel_endpoint(otel_endpoint)
        timeout = get_otel_timeout(otel_timeout)
        for attributes in [log_resource_attributes, metric_resource_attributes]:
            if attributes is not None:
                attributes[SERVICE_NAME] = "l9gpu"

        self.logger_provider = otel_log_init(
            log_resource_attributes, endpoint + "/v1/logs", timeout
        )
        self.otel_logger = logging.getLogger("l9gpu")
        otel_handler = LoggingHandler(
            level=logging._nameToLevel["INFO"], logger_provider=self.logger_provider
        )
        self.otel_logger.setLevel(logging.INFO)
        self.otel_logger.addHandler(otel_handler)
        self._otel_handler = otel_handler

        self.meter = otel_metric_init(
            metric_resource_attributes, endpoint + "/v1/metrics", timeout
        )
        self.metrics_instruments: dict[str, _Gauge] = {}

        resource_flat = _flatten_resource_attrs(
            cast(
                Dict[str, Any],
                (
                    OmegaConf.to_container(metric_resource_attributes, resolve=True)
                    if metric_resource_attributes is not None
                    else {}
                ),
            )
        )
        self._resource_labels: Dict[str, str] = {}
        for key in ("k8s.cluster.name", "host.name"):
            val = resource_flat.get(key)
            if val is not None:
                self._resource_labels[key] = str(val)

    def shutdown(self) -> None:
        """Flush and shut down the logger provider. Call this before process exit in one-shot commands."""
        self.otel_logger.removeHandler(self._otel_handler)
        self.logger_provider.force_flush()
        self.logger_provider.shutdown()

    def assert_never(self, x: Never) -> Never:
        raise AssertionError(f"Unhandled type: {type(x).__name__}")

    def write(
        self,
        data: Log,
        additional_params: SinkAdditionalParams,
    ) -> None:
        if additional_params.data_type:
            if additional_params.data_type is DataType.LOG:
                return self._write_log(data)
            elif additional_params.data_type is DataType.METRIC:
                return self._write_metric(data, additional_params)
            else:
                logger.error(
                    f"We expected log or metric, but got {additional_params.data_type}"
                )
                self.assert_never(additional_params.data_type)
        else:
            logger.error(
                f"OTel writes requires data_type to be specified: {additional_params}"
            )
            return

    def _get_or_create_gauge(self, otel_name: str, field_name: str) -> _Gauge:
        if otel_name not in self.metrics_instruments:
            self.metrics_instruments[otel_name] = self.meter.create_gauge(
                otel_name,
                description=otel_name,
                unit=get_unit(field_name),
            )
        return self.metrics_instruments[otel_name]

    def _emit_scalar(
        self,
        field_name: str,
        metric_value: float,
        base_attrs: Dict[str, str],
        emit_genai: bool,
    ) -> None:
        """Emit a scalar gauge under the primary name, plus gen_ai.* if requested."""
        otel_name = get_otel_name(field_name)
        gauge = self._get_or_create_gauge(otel_name, field_name)
        gauge.set(amount=metric_value, attributes=base_attrs or None)

        if emit_genai and field_name in FIELD_TO_GENAI_NAME:
            genai_name = FIELD_TO_GENAI_NAME[field_name]
            genai_gauge = self._get_or_create_gauge(genai_name, field_name)
            genai_attrs = {
                **base_attrs,
                **GENAI_DATA_POINT_ATTRIBUTES.get(field_name, {}),
            }
            genai_gauge.set(amount=metric_value, attributes=genai_attrs or None)

    # String fields that should become data-point attributes (not metric values).
    _STRING_ATTRIBUTE_FIELDS = {
        "model_name": "model.name",
        "model_version": "model.version",
        "collective_type": "nccl.collective.type",
    }
    # Integer fields that should become data-point attributes (not metric values).
    _INT_ATTRIBUTE_FIELDS = {
        "rank": "nccl.rank",
        "mig_instance_id": "gpu.mig.instance_id",
    }

    def _write_metric(self, data: Log, params: SinkAdditionalParams) -> None:
        emit_genai: bool = getattr(params, "emit_genai_namespace", False)

        for message in data.message:
            # Collect per-GPU identity attributes from the message (for data-point labels)
            gpu_index = getattr(message, "gpu_index", None)
            gpu_uuid = getattr(message, "gpu_uuid", None)
            gpu_model = getattr(message, "gpu_model", None)

            for field in fields(message):
                field_name = field.name
                metric_value = getattr(message, field_name)

                if metric_value is None:
                    continue

                # String fields (e.g. gpu_uuid, gpu_model) are identity attributes, not metrics
                if isinstance(metric_value, str):
                    continue

                # Integer identity fields (e.g. gpu_index) are also attributes, not metrics
                if field_name in _IDENTITY_FIELDS:
                    continue

                otel_name = get_otel_name(field_name)
                base_attrs = get_data_point_attributes(field_name)
                if gpu_index is not None:
                    base_attrs["gpu.index"] = str(gpu_index)
                if gpu_uuid is not None:
                    base_attrs["gpu.uuid"] = gpu_uuid
                if gpu_model is not None:
                    base_attrs["gpu.model"] = gpu_model

                # Add string identity fields as data-point attributes
                for attr_field, attr_key in self._STRING_ATTRIBUTE_FIELDS.items():
                    val = getattr(message, attr_field, None)
                    if val is not None:
                        base_attrs[attr_key] = str(val)
                # Add integer identity fields as data-point attributes
                for attr_field, attr_key in self._INT_ATTRIBUTE_FIELDS.items():
                    val = getattr(message, attr_field, None)
                    if val is not None:
                        base_attrs[attr_key] = str(val)
                # MIG enabled flag
                mig = getattr(message, "mig_enabled", None)
                if mig is not None:
                    base_attrs["gpu.mig.enabled"] = str(mig).lower()

                base_attrs.update(self._resource_labels)
                if params.gpu_k8s_labels and gpu_index is not None:
                    base_attrs.update(params.gpu_k8s_labels.get(gpu_index, {}))

                if isinstance(metric_value, (int, float)):
                    self._emit_scalar(field_name, metric_value, base_attrs, emit_genai)

                elif isinstance(metric_value, list):
                    # Per-element emission with link_index attribute (e.g., XGMI, network ports)
                    gauge = self._get_or_create_gauge(otel_name, field_name)
                    for idx, val in enumerate(metric_value):
                        if isinstance(val, (int, float)):
                            attrs = {
                                **base_attrs,
                                "gpu.interconnect.link_index": str(idx),
                            }
                            gauge.set(amount=val, attributes=attrs)

                elif isinstance(metric_value, dict):
                    # Per-key emission with block attribute (e.g., ECC per memory block)
                    gauge = self._get_or_create_gauge(otel_name, field_name)
                    for key, val in metric_value.items():
                        if isinstance(val, (int, float)):
                            attrs = {**base_attrs, "gpu.ecc.memory_block": key.lower()}
                            gauge.set(amount=val, attributes=attrs)

                else:
                    logger.warning(
                        f"Unsupported data type for OTel logging: {type(metric_value)}, ignoring metric {field_name}"
                    )

    def _write_log(self, data: Log) -> None:
        for message in data.message:
            msg = asdict(message, dict_factory=flatten_dict_factory)
            msg["time"] = data.ts
            self.otel_logger.info("", extra=msg)
