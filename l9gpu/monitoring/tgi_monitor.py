# Copyright (c) Last9, Inc.
"""HuggingFace Text Generation Inference (TGI) metrics collector.

Scrapes the TGI Prometheus endpoint (default :8080/metrics) and returns
a TGIMetrics instance ready to be emitted via any l9gpu sink.
"""

import logging
from typing import Optional

from l9gpu.monitoring import prometheus
from l9gpu.monitoring.vllm_monitor import _extract_histogram
from l9gpu.schemas.tgi_metrics import TGIMetrics

logger = logging.getLogger(__name__)


def scrape_tgi(endpoint: str) -> TGIMetrics:
    """Scrape TGI and return TGIMetrics.

    TGI only exposes histograms (no counters that need delta calculation),
    so no counter state is required.
    """
    try:
        samples = prometheus.scrape(endpoint)
    except Exception as exc:
        logger.error("Failed to scrape TGI endpoint %s: %s", endpoint, exc)
        return TGIMetrics()

    metrics = TGIMetrics()

    def _fill(
        metric_name: str, p50_attr: str, p95_attr: str, p99_attr: Optional[str] = None
    ) -> None:
        buckets, count = _extract_histogram(samples, metric_name)
        if not buckets:
            return
        setattr(metrics, p50_attr, prometheus.histogram_quantile(buckets, count, 0.50))
        setattr(metrics, p95_attr, prometheus.histogram_quantile(buckets, count, 0.95))
        if p99_attr:
            setattr(
                metrics, p99_attr, prometheus.histogram_quantile(buckets, count, 0.99)
            )

    _fill(
        "tgi_request_duration",
        "tgi_request_latency_p50",
        "tgi_request_latency_p95",
        p99_attr="tgi_request_latency_p99",
    )
    _fill(
        "tgi_request_queue_duration", "tgi_queue_latency_p50", "tgi_queue_latency_p95"
    )
    _fill(
        "tgi_request_inference_duration",
        "tgi_inference_latency_p50",
        "tgi_inference_latency_p95",
    )
    _fill("tgi_request_mean_time_per_token_duration", "tgi_tpot_p50", "tgi_tpot_p95")
    _fill("tgi_batch_next_size", "tgi_batch_size_p50", "tgi_batch_size_p95")
    _fill(
        "tgi_batch_forward_duration",
        "tgi_batch_forward_duration_p50",
        "tgi_batch_forward_duration_p95",
    )
    _fill("tgi_request_input_length", "tgi_input_tokens_p50", "tgi_input_tokens_p95")
    _fill(
        "tgi_request_generated_tokens", "tgi_output_tokens_p50", "tgi_output_tokens_p95"
    )

    return metrics
