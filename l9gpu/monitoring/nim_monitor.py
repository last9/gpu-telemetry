# Copyright (c) Last9, Inc.
"""NVIDIA NIM inference microservice metrics collector.

Scrapes the NIM Prometheus endpoint and returns a NimMetrics instance
ready to be emitted via any l9gpu sink.
"""

import logging
from typing import List, Tuple

from l9gpu.monitoring import prometheus
from l9gpu.schemas.nim_metrics import NimMetrics

logger = logging.getLogger(__name__)


def _extract_histogram(
    samples: prometheus.MetricSamples,
    metric_base: str,
) -> Tuple[List[Tuple[float, float]], float]:
    """Extract (buckets, count) from a Prometheus histogram metric family."""
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


def scrape_nim(endpoint: str) -> NimMetrics:
    """Scrape the NIM Prometheus endpoint and return NimMetrics."""
    try:
        samples = prometheus.scrape(endpoint)
    except Exception as exc:
        logger.error("Failed to scrape NIM endpoint %s: %s", endpoint, exc)
        return NimMetrics()

    metrics = NimMetrics()

    # Request totals (cumulative counters — emitted as gauges for simplicity)
    for _, value in samples.get("nvidia_nim_request_count", []):
        metrics.requests_total = int(value)
        break

    requests_failed = 0
    for _, value in samples.get("nvidia_nim_request_failure", []):
        requests_failed += int(value)
    if requests_failed > 0 or "nvidia_nim_request_failure" in samples:
        metrics.requests_failed = requests_failed

    # Queue depth
    for _, value in samples.get("nvidia_nim_queue_size", []):
        metrics.queue_depth = int(value)
        break

    # KV-cache utilization
    for _, value in samples.get("nvidia_nim_gpu_cache_utilization", []):
        metrics.kv_cache_usage = value
        break

    # Request latency histogram
    latency_buckets, latency_count = _extract_histogram(
        samples, "nvidia_nim_request_duration_seconds"
    )
    if latency_buckets:
        metrics.request_latency_p50 = prometheus.histogram_quantile(
            latency_buckets, latency_count, 0.50
        )
        metrics.request_latency_p99 = prometheus.histogram_quantile(
            latency_buckets, latency_count, 0.99
        )

    # Batch size — NIM may expose average via a gauge or histogram
    for _, value in samples.get("nvidia_nim_batch_size", []):
        metrics.batch_size_avg = value
        break

    # Inter-token latency histogram (NIM >= 1.1)
    itl_buckets, itl_count = _extract_histogram(
        samples, "nvidia_nim_time_per_output_token_seconds"
    )
    if itl_buckets:
        metrics.nim_itl_p50 = prometheus.histogram_quantile(
            itl_buckets, itl_count, 0.50
        )
        metrics.nim_itl_p95 = prometheus.histogram_quantile(
            itl_buckets, itl_count, 0.95
        )

    return metrics
