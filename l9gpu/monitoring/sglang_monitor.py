# Copyright (c) Last9, Inc.
"""SGLang inference engine metrics collector.

Scrapes the SGLang Prometheus endpoint and returns SGLangMetrics instances
ready to be emitted via any l9gpu sink.

Requires: SGLang started with --enable-metrics (default port 30000).
"""

import logging
from typing import Dict, Optional, Tuple

from l9gpu.monitoring import prometheus
from l9gpu.schemas.sglang_metrics import SGLangMetrics

logger = logging.getLogger(__name__)

CounterState = Dict[str, float]


def _empty_state() -> CounterState:
    return {"prompt_tokens": 0.0, "generation_tokens": 0.0}


def _rate(
    current: Optional[float], prev: Optional[float], interval: float
) -> Optional[float]:
    if current is None or prev is None or interval <= 0:
        return None
    delta = current - prev
    return None if delta < 0 else delta / interval


def scrape_sglang(
    endpoint: str,
    prev_state: Optional[CounterState],
    interval_seconds: float,
) -> Tuple[SGLangMetrics, CounterState]:
    """Scrape SGLang and return SGLangMetrics + updated counter state."""
    try:
        samples = prometheus.scrape(endpoint)
    except Exception as exc:
        logger.error("Failed to scrape SGLang endpoint %s: %s", endpoint, exc)
        return SGLangMetrics(), prev_state or _empty_state()

    # SGLang uses colon-separated metric names (e.g., "sglang:cache_hit_rate").
    # Normalize to underscore so lookups work with either convention.
    samples = {k.replace(":", "_"): v for k, v in samples.items()}

    metrics = SGLangMetrics()

    # --- Gauges ---
    for _, v in samples.get("sglang_cache_hit_rate", []):
        metrics.sglang_cache_hit_rate = v
        break

    for _, v in samples.get("sglang_num_running_reqs", []):
        metrics.sglang_requests_running = int(v)
        break

    for _, v in samples.get("sglang_num_waiting_reqs", []):
        metrics.sglang_requests_waiting = int(v)
        break

    for _, v in samples.get("sglang_num_queue_reqs", []):
        metrics.sglang_requests_waiting = int(v)
        break

    # --- Model name from labels ---
    for labels, _ in samples.get(
        "sglang_num_running_reqs", samples.get("sglang_prompt_tokens_total", [])
    ):
        mn = labels.get("model_name") or labels.get("model")
        if mn:
            metrics.model_name = mn
        break

    # --- Counters for throughput ---
    cs = _empty_state()
    for _, v in samples.get("sglang_prompt_tokens_total", []):
        cs["prompt_tokens"] = v
        break
    for _, v in samples.get("sglang_generation_tokens_total", []):
        cs["generation_tokens"] = v
        break

    if prev_state is not None:
        metrics.sglang_prompt_tokens_per_sec = _rate(
            cs["prompt_tokens"], prev_state.get("prompt_tokens"), interval_seconds
        )
        metrics.sglang_generation_tokens_per_sec = _rate(
            cs["generation_tokens"],
            prev_state.get("generation_tokens"),
            interval_seconds,
        )

    # --- Histograms ---
    itl_b, itl_c = _extract_histogram(samples, "sglang_time_per_output_token_seconds")
    if itl_b:
        metrics.sglang_itl_p50 = prometheus.histogram_quantile(itl_b, itl_c, 0.50)
        metrics.sglang_itl_p95 = prometheus.histogram_quantile(itl_b, itl_c, 0.95)

    ttft_b, ttft_c = _extract_histogram(samples, "sglang_time_to_first_token_seconds")
    if ttft_b:
        metrics.sglang_ttft_p50 = prometheus.histogram_quantile(ttft_b, ttft_c, 0.50)
        metrics.sglang_ttft_p95 = prometheus.histogram_quantile(ttft_b, ttft_c, 0.95)

    e2e_b, e2e_c = _extract_histogram(samples, "sglang_e2e_request_latency_seconds")
    if e2e_b:
        metrics.sglang_e2e_latency_p50 = prometheus.histogram_quantile(
            e2e_b, e2e_c, 0.50
        )
        metrics.sglang_e2e_latency_p95 = prometheus.histogram_quantile(
            e2e_b, e2e_c, 0.95
        )
        metrics.sglang_e2e_latency_p99 = prometheus.histogram_quantile(
            e2e_b, e2e_c, 0.99
        )

    return metrics, cs


def _extract_histogram(samples, base):
    """Thin wrapper matching the vllm_monitor helper signature."""
    from l9gpu.monitoring.vllm_monitor import _extract_histogram as _vllm_hist

    return _vllm_hist(samples, base)
