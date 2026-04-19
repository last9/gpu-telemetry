# Copyright (c) Last9, Inc.
"""Unit tests for the HuggingFace TGI metrics collector."""

from l9gpu.monitoring import tgi_monitor

_TGI_PROM_TEXT = """\
# TYPE tgi_request_duration_bucket histogram
tgi_request_duration_bucket{le="0.5"} 200
tgi_request_duration_bucket{le="1.0"} 600
tgi_request_duration_bucket{le="2.0"} 900
tgi_request_duration_bucket{le="5.0"} 980
tgi_request_duration_bucket{le="+Inf"} 1000
# TYPE tgi_request_duration_count counter
tgi_request_duration_count 1000
# TYPE tgi_request_queue_duration_bucket histogram
tgi_request_queue_duration_bucket{le="0.01"} 500
tgi_request_queue_duration_bucket{le="0.1"} 900
tgi_request_queue_duration_bucket{le="1.0"} 990
tgi_request_queue_duration_bucket{le="+Inf"} 1000
# TYPE tgi_request_queue_duration_count counter
tgi_request_queue_duration_count 1000
# TYPE tgi_request_inference_duration_bucket histogram
tgi_request_inference_duration_bucket{le="0.1"} 300
tgi_request_inference_duration_bucket{le="0.5"} 800
tgi_request_inference_duration_bucket{le="1.0"} 980
tgi_request_inference_duration_bucket{le="+Inf"} 1000
# TYPE tgi_request_inference_duration_count counter
tgi_request_inference_duration_count 1000
# TYPE tgi_request_mean_time_per_token_duration_bucket histogram
tgi_request_mean_time_per_token_duration_bucket{le="0.01"} 100
tgi_request_mean_time_per_token_duration_bucket{le="0.05"} 700
tgi_request_mean_time_per_token_duration_bucket{le="0.1"} 950
tgi_request_mean_time_per_token_duration_bucket{le="+Inf"} 1000
# TYPE tgi_request_mean_time_per_token_duration_count counter
tgi_request_mean_time_per_token_duration_count 1000
# TYPE tgi_batch_next_size_bucket histogram
tgi_batch_next_size_bucket{le="4"} 300
tgi_batch_next_size_bucket{le="8"} 700
tgi_batch_next_size_bucket{le="16"} 950
tgi_batch_next_size_bucket{le="+Inf"} 1000
# TYPE tgi_batch_next_size_count counter
tgi_batch_next_size_count 1000
"""


def test_all_histograms_extracted(monkeypatch):
    from l9gpu.monitoring import prometheus

    monkeypatch.setattr(
        prometheus, "scrape", lambda url, **kw: prometheus.parse(_TGI_PROM_TEXT)
    )

    metrics = tgi_monitor.scrape_tgi("http://fake:8080/metrics")
    assert metrics.tgi_request_latency_p50 is not None
    assert metrics.tgi_request_latency_p95 is not None
    assert metrics.tgi_request_latency_p99 is not None
    assert metrics.tgi_queue_latency_p50 is not None
    assert metrics.tgi_inference_latency_p50 is not None
    assert metrics.tgi_tpot_p50 is not None
    assert metrics.tgi_batch_size_p50 is not None


def test_empty_endpoint_returns_empty(monkeypatch):
    from l9gpu.monitoring import prometheus

    monkeypatch.setattr(prometheus, "scrape", lambda url, **kw: {})

    metrics = tgi_monitor.scrape_tgi("http://fake:8080/metrics")
    assert metrics.tgi_request_latency_p50 is None
    assert metrics.tgi_tpot_p50 is None


def test_scrape_failure(monkeypatch):
    from l9gpu.monitoring import prometheus

    monkeypatch.setattr(
        prometheus,
        "scrape",
        lambda url, **kw: (_ for _ in ()).throw(ConnectionError("down")),
    )

    metrics = tgi_monitor.scrape_tgi("http://fake:8080/metrics")
    assert metrics.tgi_request_latency_p50 is None
