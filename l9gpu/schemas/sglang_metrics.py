# Copyright (c) Last9, Inc.
"""Schema for SGLang inference engine metrics.

All field names use the sglang_ prefix to avoid collisions with
VllmMetrics fields that share the same logical names (itl_p50, ttft_p50, etc.)
in the flat FIELD_TO_OTEL_NAME registry.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class SGLangMetrics:
    """Metrics emitted by a running SGLang server.

    Scraped from http://localhost:30000/metrics (Prometheus, sglang_ prefix).
    Enable with --enable-metrics when starting the SGLang server.
    """

    # Throughput (tokens/s) — derived from counter deltas
    sglang_prompt_tokens_per_sec: Optional[float] = None
    sglang_generation_tokens_per_sec: Optional[float] = None

    # Cache effectiveness (gauge 0–1; SGLang uses RadixAttention prefix sharing)
    sglang_cache_hit_rate: Optional[float] = None

    # Inter-token latency (seconds) from sglang_time_per_output_token_seconds
    sglang_itl_p50: Optional[float] = None
    sglang_itl_p95: Optional[float] = None

    # Time-to-first-token (seconds)
    sglang_ttft_p50: Optional[float] = None
    sglang_ttft_p95: Optional[float] = None

    # End-to-end request latency (seconds)
    sglang_e2e_latency_p50: Optional[float] = None
    sglang_e2e_latency_p95: Optional[float] = None
    sglang_e2e_latency_p99: Optional[float] = None

    # Request queue depths
    sglang_requests_running: Optional[int] = None
    sglang_requests_waiting: Optional[int] = None

    # Model name (from Prometheus labels)
    model_name: Optional[str] = None
