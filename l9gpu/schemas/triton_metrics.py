# Copyright (c) Last9, Inc.
"""Schema for NVIDIA Triton Inference Server metrics.

All field names use the triton_ prefix to avoid collisions with NIM and vLLM
fields that share logical names (queue_depth, requests_success_per_sec) in
the flat FIELD_TO_OTEL_NAME registry.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class TritonMetrics:
    """Per-model metrics from Triton Inference Server.

    Scraped from http://localhost:8002/metrics (Prometheus format).
    One instance per (model_name, model_version) pair.

    Rate fields are derived from counter deltas between scrape cycles.
    Average latency fields are derived as cumulative_duration / request_count.
    """

    # Identity fields (not emitted as metrics — used as data-point attributes)
    model_name: Optional[str] = None
    model_version: Optional[str] = None

    # Request rates (requests/s) — derived from counter deltas
    triton_requests_success_per_sec: Optional[float] = None
    triton_requests_failed_per_sec: Optional[float] = None

    # Average latency components (microseconds) — duration_delta / request_delta
    triton_avg_request_latency_us: Optional[float] = None
    triton_avg_queue_latency_us: Optional[float] = None
    triton_avg_compute_input_latency_us: Optional[float] = None
    triton_avg_compute_infer_latency_us: Optional[float] = None
    triton_avg_compute_output_latency_us: Optional[float] = None

    # Queue depth (instantaneous gauge)
    triton_queue_depth: Optional[int] = None

    # Batch efficiency — model executions per request (higher = better batching)
    triton_avg_batch_size: Optional[float] = None
