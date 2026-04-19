# Copyright (c) Last9, Inc.
"""Triton Inference Server metrics collector.

Scrapes the Triton Prometheus endpoint (default :8002/metrics) and returns
per-model TritonMetrics instances ready to be emitted via any l9gpu sink.
"""

import logging
from typing import Dict, List, Optional, Tuple

from l9gpu.monitoring import prometheus
from l9gpu.schemas.triton_metrics import TritonMetrics

logger = logging.getLogger(__name__)

# Counter state keyed by (model_name, model_version)
ModelKey = Tuple[str, str]
_COUNTER_FIELDS = [
    "request_success",
    "request_failure",
    "request_duration_us",
    "queue_duration_us",
    "compute_input_duration_us",
    "compute_infer_duration_us",
    "compute_output_duration_us",
    "exec_count",
    "inference_count",
]
CounterSnapshot = Dict[str, float]
TritonCounterState = Dict[ModelKey, CounterSnapshot]


def _empty_snapshot() -> CounterSnapshot:
    return {k: 0.0 for k in _COUNTER_FIELDS}


def _rate(current: float, prev: float, interval: float) -> Optional[float]:
    delta = current - prev
    if delta < 0 or interval <= 0:
        return None
    return delta / interval


def _latency_avg(
    duration_current: float,
    duration_prev: float,
    requests_current: float,
    requests_prev: float,
) -> Optional[float]:
    """Average latency = duration_delta / request_delta."""
    dur_delta = duration_current - duration_prev
    req_delta = requests_current - requests_prev
    if req_delta <= 0 or dur_delta < 0:
        return None
    return dur_delta / req_delta


def scrape_triton(
    endpoint: str,
    prev_state: Optional[TritonCounterState],
    interval_seconds: float,
) -> Tuple[List[TritonMetrics], TritonCounterState]:
    """Scrape Triton and return one TritonMetrics per (model, version) pair.

    Returns (metrics_list, new_counter_state).
    Pass prev_state=None on the first scrape — rate/average fields will be None.
    """
    try:
        samples = prometheus.scrape(endpoint)
    except Exception as exc:
        logger.error("Failed to scrape Triton endpoint %s: %s", endpoint, exc)
        return [], prev_state or {}

    # Accumulate per-model counters from Prometheus samples
    # Triton labels: model="<name>", version="<ver>"
    current_state: TritonCounterState = {}

    def _add(metric_name: str, field: str) -> None:
        for labels, value in samples.get(metric_name, []):
            model = labels.get("model", "")
            version = labels.get("version", "1")
            key: ModelKey = (model, version)
            snap = current_state.setdefault(key, _empty_snapshot())
            snap[field] = snap.get(field, 0.0) + value

    _add("nv_inference_request_success", "request_success")
    _add("nv_inference_request_failure", "request_failure")
    _add("nv_inference_request_duration_us", "request_duration_us")
    _add("nv_inference_queue_duration_us", "queue_duration_us")
    _add("nv_inference_compute_input_duration_us", "compute_input_duration_us")
    _add("nv_inference_compute_infer_duration_us", "compute_infer_duration_us")
    _add("nv_inference_compute_output_duration_us", "compute_output_duration_us")
    _add("nv_inference_exec_count", "exec_count")
    _add("nv_inference_count", "inference_count")

    # Queue depth is a gauge — read separately
    queue_depths: Dict[ModelKey, int] = {}
    for labels, value in samples.get("nv_inference_pending_request_count", []):
        model = labels.get("model", "")
        version = labels.get("version", "1")
        queue_depths[(model, version)] = int(value)

    result: List[TritonMetrics] = []
    for key, snap in current_state.items():
        model_name, model_version = key
        prev = (prev_state or {}).get(key, _empty_snapshot())

        metrics = TritonMetrics(
            model_name=model_name,
            model_version=model_version,
            triton_queue_depth=queue_depths.get(key),
        )

        if prev_state is not None:
            metrics.triton_requests_success_per_sec = _rate(
                snap["request_success"], prev["request_success"], interval_seconds
            )
            metrics.triton_requests_failed_per_sec = _rate(
                snap["request_failure"], prev["request_failure"], interval_seconds
            )
            metrics.triton_avg_request_latency_us = _latency_avg(
                snap["request_duration_us"],
                prev["request_duration_us"],
                snap["request_success"],
                prev["request_success"],
            )
            metrics.triton_avg_queue_latency_us = _latency_avg(
                snap["queue_duration_us"],
                prev["queue_duration_us"],
                snap["request_success"],
                prev["request_success"],
            )
            metrics.triton_avg_compute_input_latency_us = _latency_avg(
                snap["compute_input_duration_us"],
                prev["compute_input_duration_us"],
                snap["request_success"],
                prev["request_success"],
            )
            metrics.triton_avg_compute_infer_latency_us = _latency_avg(
                snap["compute_infer_duration_us"],
                prev["compute_infer_duration_us"],
                snap["request_success"],
                prev["request_success"],
            )
            metrics.triton_avg_compute_output_latency_us = _latency_avg(
                snap["compute_output_duration_us"],
                prev["compute_output_duration_us"],
                snap["request_success"],
                prev["request_success"],
            )

            # avg_batch_size = inferences_delta / exec_count_delta
            infer_delta = snap["inference_count"] - prev["inference_count"]
            exec_delta = snap["exec_count"] - prev["exec_count"]
            if exec_delta > 0 and infer_delta >= 0:
                metrics.triton_avg_batch_size = infer_delta / exec_delta

        result.append(metrics)

    return result, current_state
