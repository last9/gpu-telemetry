# Copyright (c) Last9, Inc.
"""Schema for NVIDIA NIM inference microservice metrics."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class NimMetrics:
    """Metrics emitted by a running NVIDIA NIM container.

    Populated by scraping the NIM Prometheus endpoint
    (default: http://localhost:8000/metrics).

    Latency fields are P50/P99 estimated from histogram buckets.
    """

    # Request counters (cumulative)
    requests_total: Optional[int] = None
    requests_failed: Optional[int] = None

    # Request latency (seconds)
    request_latency_p50: Optional[float] = None
    request_latency_p99: Optional[float] = None

    # Batch execution
    batch_size_avg: Optional[float] = None
    queue_depth: Optional[int] = None

    # GPU KV-cache utilization (fraction 0–1)
    kv_cache_usage: Optional[float] = None

    # Phase 8: Inter-token latency (seconds) — from NIM histogram (if available)
    nim_itl_p50: Optional[float] = None
    nim_itl_p95: Optional[float] = None
