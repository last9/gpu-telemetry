# Copyright (c) Last9, Inc.
"""Unit tests for the SGLang inference engine metrics collector."""

import pytest
from l9gpu.monitoring import sglang_monitor

_SGLANG_PROM_TEXT = """\
# TYPE sglang_prompt_tokens_total counter
sglang_prompt_tokens_total 50000
# TYPE sglang_generation_tokens_total counter
sglang_generation_tokens_total 20000
# TYPE sglang_cache_hit_rate gauge
sglang_cache_hit_rate 0.73
# TYPE sglang_num_running_reqs gauge
sglang_num_running_reqs 5
# TYPE sglang_num_waiting_reqs gauge
sglang_num_waiting_reqs 2
# TYPE sglang_time_per_output_token_seconds_bucket histogram
sglang_time_per_output_token_seconds_bucket{le="0.01"} 100
sglang_time_per_output_token_seconds_bucket{le="0.05"} 800
sglang_time_per_output_token_seconds_bucket{le="0.1"} 950
sglang_time_per_output_token_seconds_bucket{le="+Inf"} 1000
# TYPE sglang_time_per_output_token_seconds_count counter
sglang_time_per_output_token_seconds_count 1000
# TYPE sglang_time_to_first_token_seconds_bucket histogram
sglang_time_to_first_token_seconds_bucket{le="0.1"} 200
sglang_time_to_first_token_seconds_bucket{le="0.5"} 900
sglang_time_to_first_token_seconds_bucket{le="1.0"} 990
sglang_time_to_first_token_seconds_bucket{le="+Inf"} 1000
# TYPE sglang_time_to_first_token_seconds_count counter
sglang_time_to_first_token_seconds_count 1000
# TYPE sglang_e2e_request_latency_seconds_bucket histogram
sglang_e2e_request_latency_seconds_bucket{le="1.0"} 500
sglang_e2e_request_latency_seconds_bucket{le="5.0"} 950
sglang_e2e_request_latency_seconds_bucket{le="10.0"} 990
sglang_e2e_request_latency_seconds_bucket{le="+Inf"} 1000
# TYPE sglang_e2e_request_latency_seconds_count counter
sglang_e2e_request_latency_seconds_count 1000
"""


def test_first_scrape_no_throughput(monkeypatch):
    from l9gpu.monitoring import prometheus

    monkeypatch.setattr(
        prometheus, "scrape", lambda url, **kw: prometheus.parse(_SGLANG_PROM_TEXT)
    )

    metrics, state = sglang_monitor.scrape_sglang(
        "http://fake:30000/metrics", None, 30.0
    )
    assert metrics.sglang_prompt_tokens_per_sec is None
    assert metrics.sglang_cache_hit_rate == pytest.approx(0.73)
    assert metrics.sglang_requests_running == 5
    assert metrics.sglang_requests_waiting == 2


def test_second_scrape_computes_throughput(monkeypatch):
    from l9gpu.monitoring import prometheus

    monkeypatch.setattr(
        prometheus, "scrape", lambda url, **kw: prometheus.parse(_SGLANG_PROM_TEXT)
    )

    prev = {"prompt_tokens": 49000.0, "generation_tokens": 19500.0}
    metrics, state = sglang_monitor.scrape_sglang(
        "http://fake:30000/metrics", prev, 30.0
    )

    assert metrics.sglang_prompt_tokens_per_sec is not None
    assert abs(metrics.sglang_prompt_tokens_per_sec - 1000.0 / 30.0) < 0.1
    assert abs(metrics.sglang_generation_tokens_per_sec - 500.0 / 30.0) < 0.1


def test_histograms_populated(monkeypatch):
    from l9gpu.monitoring import prometheus

    monkeypatch.setattr(
        prometheus, "scrape", lambda url, **kw: prometheus.parse(_SGLANG_PROM_TEXT)
    )

    metrics, _ = sglang_monitor.scrape_sglang("http://fake:30000/metrics", None, 30.0)
    assert metrics.sglang_itl_p50 is not None
    assert metrics.sglang_ttft_p50 is not None
    assert metrics.sglang_e2e_latency_p50 is not None
    assert metrics.sglang_e2e_latency_p99 is not None
