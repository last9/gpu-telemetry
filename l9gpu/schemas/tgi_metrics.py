# Copyright (c) Last9, Inc.
"""Schema for HuggingFace Text Generation Inference (TGI) metrics.

All field names use the tgi_ prefix to avoid collisions in the flat
FIELD_TO_OTEL_NAME registry.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class TGIMetrics:
    """Metrics emitted by a running TGI server.

    Scraped from http://localhost:8080/metrics (Prometheus, tgi_ prefix).
    All latency fields are percentiles derived from histogram buckets.
    """

    # End-to-end request latency (seconds)
    tgi_request_latency_p50: Optional[float] = None
    tgi_request_latency_p95: Optional[float] = None
    tgi_request_latency_p99: Optional[float] = None

    # Time spent in request queue (seconds)
    tgi_queue_latency_p50: Optional[float] = None
    tgi_queue_latency_p95: Optional[float] = None

    # Pure inference latency (seconds) — GPU compute only
    tgi_inference_latency_p50: Optional[float] = None
    tgi_inference_latency_p95: Optional[float] = None

    # Mean time per output token (seconds) — equivalent to TPOT/ITL
    tgi_tpot_p50: Optional[float] = None
    tgi_tpot_p95: Optional[float] = None

    # Batch sizes
    tgi_batch_size_p50: Optional[float] = None
    tgi_batch_size_p95: Optional[float] = None

    # Batch forward pass duration (seconds)
    tgi_batch_forward_duration_p50: Optional[float] = None
    tgi_batch_forward_duration_p95: Optional[float] = None

    # Token distributions
    tgi_input_tokens_p50: Optional[float] = None
    tgi_input_tokens_p95: Optional[float] = None
    tgi_output_tokens_p50: Optional[float] = None
    tgi_output_tokens_p95: Optional[float] = None
