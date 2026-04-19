# Copyright (c) Last9, Inc.
"""Schema for vLLM inference engine metrics scraped from the vLLM Prometheus endpoint."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class VllmMetrics:
    """Metrics emitted by a running vLLM server.

    Populated by scraping the vLLM Prometheus endpoint
    (default: http://localhost:8000/metrics).

    Throughput fields (tokens/s) are computed as the rate of change of
    cumulative counters between successive scrape intervals.
    Latency fields are approximated as P50/P95/P99 from histogram buckets.
    """

    # Throughput (tokens/s) — derived from counter deltas
    prompt_tokens_per_sec: Optional[float] = None
    generation_tokens_per_sec: Optional[float] = None

    # End-to-end request latency (seconds)
    e2e_latency_p50: Optional[float] = None
    e2e_latency_p95: Optional[float] = None
    e2e_latency_p99: Optional[float] = None

    # Time-to-first-token (seconds)
    ttft_p50: Optional[float] = None
    ttft_p95: Optional[float] = None

    # KV-cache utilization (fraction 0–1)
    gpu_cache_usage: Optional[float] = None
    cpu_cache_usage: Optional[float] = None

    # Request queue depths
    requests_running: Optional[int] = None
    requests_waiting: Optional[int] = None
    requests_swapped: Optional[int] = None

    # --- Phase 8: extended inference metrics ---

    # Inter-token latency (seconds) — from vllm:time_per_output_token_seconds histogram
    itl_p50: Optional[float] = None
    itl_p95: Optional[float] = None
    itl_p99: Optional[float] = None

    # Disaggregated prefill / decode duration (seconds) — vLLM v0.8+
    prefill_duration_p50: Optional[float] = None
    prefill_duration_p95: Optional[float] = None
    decode_duration_p50: Optional[float] = None
    decode_duration_p95: Optional[float] = None

    # Prefix cache hit rate (fraction 0–1)
    # Computed from counter-delta: prefix_cache_hits / prefix_cache_queries (v0.8+)
    # Falls back to deprecated gpu_prefix_cache_hit_rate gauge on older vLLM.
    cache_hit_rate: Optional[float] = None

    # KV cache eviction count (events/s)
    cache_evictions_per_sec: Optional[float] = None

    # Speculative decoding — computed from counter deltas
    # acceptance_rate = num_accepted_tokens_total / num_draft_tokens_total
    spec_decode_acceptance_rate: Optional[float] = None
    # efficiency = 1 + (num_accepted_tokens_total / num_drafts)  (mean acceptance length)
    spec_decode_efficiency: Optional[float] = None

    # Request success (requests/s) by finish reason
    requests_success_per_sec: Optional[float] = None
    requests_finished_stop_per_sec: Optional[float] = None
    requests_finished_length_per_sec: Optional[float] = None
    requests_finished_abort_per_sec: Optional[float] = None

    # Preemption count (events/s) — continuous batching pressure signal
    preemptions_per_sec: Optional[float] = None

    # LoRA adapter metrics (optional — only when LoRA adapters are loaded)
    lora_active_count: Optional[int] = None

    # Model name (from vLLM Prometheus labels, for multi-model deployments)
    model_name: Optional[str] = None
