# Copyright (c) Last9, Inc.
"""vLLM inference engine metrics collector.

Scrapes the vLLM Prometheus endpoint and returns a VllmMetrics instance
ready to be emitted via any l9gpu sink.
"""

import logging
from typing import Dict, List, Optional, Tuple

from l9gpu.monitoring import prometheus
from l9gpu.schemas.vllm_metrics import VllmMetrics

logger = logging.getLogger(__name__)


def _extract_histogram(
    samples: prometheus.MetricSamples,
    metric_base: str,
) -> Tuple[List[Tuple[float, float]], float]:
    """Extract (buckets, count) from a Prometheus histogram metric family.

    Returns a list of (le_float, cumulative_count) pairs and the total count.
    """
    buckets: List[Tuple[float, float]] = []
    count = 0.0
    for labels, value in samples.get(f"{metric_base}_bucket", []):
        le_str = labels.get("le", "")
        try:
            le = float(le_str)
        except ValueError:
            continue
        buckets.append((le, value))
    for _, value in samples.get(f"{metric_base}_count", []):
        count = value
        break
    return buckets, count


# Keys used for counter-state tracking across scrape cycles.
_COUNTER_KEYS = [
    "prompt_tokens",
    "generation_tokens",
    "prefix_cache_hits",
    "prefix_cache_queries",
    "spec_accepted",
    "spec_draft",
    "spec_drafts",
    "preemptions",
    "request_success",
    "request_stop",
    "request_length",
    "request_abort",
    "cache_evictions",
]

CounterState = Dict[str, float]


def _empty_counter_state() -> CounterState:
    return {k: 0.0 for k in _COUNTER_KEYS}


def _read_counter(samples: prometheus.MetricSamples, name: str) -> Optional[float]:
    """Read a single counter value (first sample only)."""
    for _, value in samples.get(name, []):
        return value
    return None


def _read_gauge(samples: prometheus.MetricSamples, name: str) -> Optional[float]:
    """Read a single gauge value (first sample only)."""
    for _, value in samples.get(name, []):
        return value
    return None


def _counter_rate(
    current: Optional[float],
    prev: Optional[float],
    interval: float,
) -> Optional[float]:
    """Compute rate from counter delta.  Returns None if data is missing."""
    if current is None or prev is None or interval <= 0:
        return None
    delta = current - prev
    if delta < 0:
        return None  # counter reset
    return delta / interval


def _counter_ratio(
    numerator_current: Optional[float],
    numerator_prev: Optional[float],
    denominator_current: Optional[float],
    denominator_prev: Optional[float],
) -> Optional[float]:
    """Compute ratio from two counter deltas (e.g. hit_rate = hits / queries)."""
    if (
        numerator_current is None
        or numerator_prev is None
        or denominator_current is None
        or denominator_prev is None
    ):
        return None
    num_delta = numerator_current - numerator_prev
    den_delta = denominator_current - denominator_prev
    if den_delta <= 0 or num_delta < 0:
        return None
    return min(1.0, num_delta / den_delta)


def scrape_vllm(
    endpoint: str,
    prev_counters: Optional[CounterState],
    interval_seconds: float,
) -> Tuple[VllmMetrics, CounterState]:
    """Scrape the vLLM Prometheus endpoint and return VllmMetrics.

    Returns (metrics, counter_state) so the caller can track counters
    for rate calculation on the next scrape.

    Pass ``None`` for ``prev_counters`` on the first call — all rate
    and delta-derived fields will be None.
    """
    try:
        samples = prometheus.scrape(endpoint)
    except Exception as exc:
        logger.error("Failed to scrape vLLM endpoint %s: %s", endpoint, exc)
        return VllmMetrics(), prev_counters or _empty_counter_state()

    metrics = VllmMetrics()

    # --- Model name (from labels on any metric that carries model_name) ---
    for labels, _ in samples.get("vllm:num_requests_running", []):
        mn = labels.get("model_name")
        if mn:
            metrics.model_name = mn
        break

    # --- Queue depths ---
    for _, value in samples.get("vllm:num_requests_running", []):
        metrics.requests_running = int(value)
        break
    for _, value in samples.get("vllm:num_requests_waiting", []):
        metrics.requests_waiting = int(value)
        break
    for _, value in samples.get("vllm:num_requests_swapped", []):
        metrics.requests_swapped = int(value)
        break

    # --- Cache utilization (gauge) ---
    for _, value in samples.get(
        "vllm:gpu_cache_usage_perc", samples.get("vllm:kv_cache_usage_perc", [])
    ):
        metrics.gpu_cache_usage = value
        break
    for _, value in samples.get("vllm:cpu_cache_usage_perc", []):
        metrics.cpu_cache_usage = value
        break

    # --- Read all counters ---
    cs: CounterState = _empty_counter_state()
    cs["prompt_tokens"] = _read_counter(samples, "vllm:prompt_tokens_total") or 0.0
    cs["generation_tokens"] = (
        _read_counter(samples, "vllm:generation_tokens_total") or 0.0
    )
    cs["prefix_cache_hits"] = (
        _read_counter(samples, "vllm:prefix_cache_hits_total") or 0.0
    )
    cs["prefix_cache_queries"] = (
        _read_counter(samples, "vllm:prefix_cache_queries_total") or 0.0
    )
    cs["cache_evictions"] = (
        _read_counter(samples, "vllm:prefix_cache_evictions_total") or 0.0
    )
    cs["spec_accepted"] = (
        _read_counter(samples, "vllm:spec_decode_num_accepted_tokens_total") or 0.0
    )
    cs["spec_draft"] = (
        _read_counter(samples, "vllm:spec_decode_num_draft_tokens_total") or 0.0
    )
    cs["spec_drafts"] = _read_counter(samples, "vllm:spec_decode_num_drafts") or 0.0
    cs["preemptions"] = _read_counter(samples, "vllm:num_preemptions_total") or 0.0

    # Request success counters by finish_reason label
    for labels, value in samples.get("vllm:request_success_total", []):
        reason = labels.get("finished_reason", labels.get("finish_reason", ""))
        if reason == "stop":
            cs["request_stop"] = value
        elif reason == "length":
            cs["request_length"] = value
        elif reason == "abort":
            cs["request_abort"] = value
        cs["request_success"] = cs.get("request_success", 0.0) + value

    # --- Throughput (tokens/s) from counter deltas ---
    if prev_counters is not None:
        metrics.prompt_tokens_per_sec = _counter_rate(
            cs["prompt_tokens"], prev_counters.get("prompt_tokens"), interval_seconds
        )
        metrics.generation_tokens_per_sec = _counter_rate(
            cs["generation_tokens"],
            prev_counters.get("generation_tokens"),
            interval_seconds,
        )

        # Prefix cache hit rate (counter-delta for v0.8+)
        metrics.cache_hit_rate = _counter_ratio(
            cs["prefix_cache_hits"],
            prev_counters.get("prefix_cache_hits"),
            cs["prefix_cache_queries"],
            prev_counters.get("prefix_cache_queries"),
        )

        # Fall back to deprecated gauge if counter-delta yielded nothing
        if metrics.cache_hit_rate is None:
            metrics.cache_hit_rate = _read_gauge(
                samples, "vllm:gpu_prefix_cache_hit_rate"
            )

        # Cache eviction rate
        metrics.cache_evictions_per_sec = _counter_rate(
            cs["cache_evictions"],
            prev_counters.get("cache_evictions"),
            interval_seconds,
        )

        # Speculative decoding
        metrics.spec_decode_acceptance_rate = _counter_ratio(
            cs["spec_accepted"],
            prev_counters.get("spec_accepted"),
            cs["spec_draft"],
            prev_counters.get("spec_draft"),
        )
        # Efficiency = 1 + mean_accepted_per_draft = 1 + accepted_delta / drafts_delta
        accepted_delta = cs["spec_accepted"] - prev_counters.get("spec_accepted", 0.0)
        drafts_delta = cs["spec_drafts"] - prev_counters.get("spec_drafts", 0.0)
        if drafts_delta > 0 and accepted_delta >= 0:
            metrics.spec_decode_efficiency = 1.0 + (accepted_delta / drafts_delta)

        # Preemption rate
        metrics.preemptions_per_sec = _counter_rate(
            cs["preemptions"], prev_counters.get("preemptions"), interval_seconds
        )

        # Request success rates
        metrics.requests_success_per_sec = _counter_rate(
            cs["request_success"],
            prev_counters.get("request_success"),
            interval_seconds,
        )
        metrics.requests_finished_stop_per_sec = _counter_rate(
            cs["request_stop"], prev_counters.get("request_stop"), interval_seconds
        )
        metrics.requests_finished_length_per_sec = _counter_rate(
            cs["request_length"], prev_counters.get("request_length"), interval_seconds
        )
        metrics.requests_finished_abort_per_sec = _counter_rate(
            cs["request_abort"], prev_counters.get("request_abort"), interval_seconds
        )

    # --- Histograms ---

    # E2E request latency
    e2e_buckets, e2e_count = _extract_histogram(
        samples, "vllm:e2e_request_latency_seconds"
    )
    if e2e_buckets:
        metrics.e2e_latency_p50 = prometheus.histogram_quantile(
            e2e_buckets, e2e_count, 0.50
        )
        metrics.e2e_latency_p95 = prometheus.histogram_quantile(
            e2e_buckets, e2e_count, 0.95
        )
        metrics.e2e_latency_p99 = prometheus.histogram_quantile(
            e2e_buckets, e2e_count, 0.99
        )

    # Time-to-first-token
    ttft_buckets, ttft_count = _extract_histogram(
        samples, "vllm:time_to_first_token_seconds"
    )
    if ttft_buckets:
        metrics.ttft_p50 = prometheus.histogram_quantile(ttft_buckets, ttft_count, 0.50)
        metrics.ttft_p95 = prometheus.histogram_quantile(ttft_buckets, ttft_count, 0.95)

    # Inter-token latency (vLLM v0.7+)
    itl_buckets, itl_count = _extract_histogram(
        samples, "vllm:time_per_output_token_seconds"
    )
    if itl_buckets:
        metrics.itl_p50 = prometheus.histogram_quantile(itl_buckets, itl_count, 0.50)
        metrics.itl_p95 = prometheus.histogram_quantile(itl_buckets, itl_count, 0.95)
        metrics.itl_p99 = prometheus.histogram_quantile(itl_buckets, itl_count, 0.99)

    # Disaggregated prefill / decode duration (vLLM v0.8+)
    pf_buckets, pf_count = _extract_histogram(
        samples, "vllm:request_prefill_time_seconds"
    )
    if pf_buckets:
        metrics.prefill_duration_p50 = prometheus.histogram_quantile(
            pf_buckets, pf_count, 0.50
        )
        metrics.prefill_duration_p95 = prometheus.histogram_quantile(
            pf_buckets, pf_count, 0.95
        )

    dc_buckets, dc_count = _extract_histogram(
        samples, "vllm:request_decode_time_seconds"
    )
    if dc_buckets:
        metrics.decode_duration_p50 = prometheus.histogram_quantile(
            dc_buckets, dc_count, 0.50
        )
        metrics.decode_duration_p95 = prometheus.histogram_quantile(
            dc_buckets, dc_count, 0.95
        )

    # LoRA adapter count (vLLM with --enable-lora)
    for _, value in samples.get("vllm:lora_requests_running", []):
        metrics.lora_active_count = int(value)
        break

    return metrics, cs
