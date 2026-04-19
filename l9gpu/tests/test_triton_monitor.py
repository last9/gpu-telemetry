# Copyright (c) Last9, Inc.
"""Unit tests for the Triton Inference Server metrics collector."""

from l9gpu.monitoring.triton_monitor import (
    scrape_triton,
    TritonCounterState,
)

# Fake Prometheus text for two models
_TRITON_PROM_TEXT = """\
# HELP nv_inference_request_success Number of successful inference requests
# TYPE nv_inference_request_success counter
nv_inference_request_success{model="llama",version="1"} 1000
nv_inference_request_success{model="mistral",version="1"} 500
# HELP nv_inference_request_failure Number of failed inference requests
# TYPE nv_inference_request_failure counter
nv_inference_request_failure{model="llama",version="1"} 5
nv_inference_request_failure{model="mistral",version="1"} 2
# HELP nv_inference_request_duration_us Cumulative request duration
# TYPE nv_inference_request_duration_us counter
nv_inference_request_duration_us{model="llama",version="1"} 5000000
nv_inference_request_duration_us{model="mistral",version="1"} 2000000
# HELP nv_inference_queue_duration_us Cumulative queue duration
# TYPE nv_inference_queue_duration_us counter
nv_inference_queue_duration_us{model="llama",version="1"} 100000
nv_inference_queue_duration_us{model="mistral",version="1"} 50000
# HELP nv_inference_compute_infer_duration_us Cumulative compute duration
# TYPE nv_inference_compute_infer_duration_us counter
nv_inference_compute_infer_duration_us{model="llama",version="1"} 4000000
nv_inference_compute_infer_duration_us{model="mistral",version="1"} 1500000
# HELP nv_inference_compute_input_duration_us Cumulative input duration
# TYPE nv_inference_compute_input_duration_us counter
nv_inference_compute_input_duration_us{model="llama",version="1"} 200000
nv_inference_compute_input_duration_us{model="mistral",version="1"} 100000
# HELP nv_inference_compute_output_duration_us Cumulative output duration
# TYPE nv_inference_compute_output_duration_us counter
nv_inference_compute_output_duration_us{model="llama",version="1"} 300000
nv_inference_compute_output_duration_us{model="mistral",version="1"} 150000
# HELP nv_inference_exec_count Number of model executions
# TYPE nv_inference_exec_count counter
nv_inference_exec_count{model="llama",version="1"} 200
nv_inference_exec_count{model="mistral",version="1"} 100
# HELP nv_inference_count Number of inferences
# TYPE nv_inference_count counter
nv_inference_count{model="llama",version="1"} 1000
nv_inference_count{model="mistral",version="1"} 500
# HELP nv_inference_pending_request_count Pending requests
# TYPE nv_inference_pending_request_count gauge
nv_inference_pending_request_count{model="llama",version="1"} 3
nv_inference_pending_request_count{model="mistral",version="1"} 0
"""


def _make_prev_state() -> TritonCounterState:
    """Build a prev_state representing counters from a previous scrape."""
    return {
        ("llama", "1"): {
            "request_success": 900.0,
            "request_failure": 4.0,
            "request_duration_us": 4500000.0,
            "queue_duration_us": 90000.0,
            "compute_input_duration_us": 180000.0,
            "compute_infer_duration_us": 3600000.0,
            "compute_output_duration_us": 270000.0,
            "exec_count": 180.0,
            "inference_count": 900.0,
        },
        ("mistral", "1"): {
            "request_success": 450.0,
            "request_failure": 1.0,
            "request_duration_us": 1800000.0,
            "queue_duration_us": 45000.0,
            "compute_input_duration_us": 90000.0,
            "compute_infer_duration_us": 1350000.0,
            "compute_output_duration_us": 135000.0,
            "exec_count": 90.0,
            "inference_count": 450.0,
        },
    }


def test_first_scrape_returns_none_rates(monkeypatch):
    """First scrape (no prev_state) should return None for all rate/average fields."""
    from l9gpu.monitoring import prometheus

    monkeypatch.setattr(
        prometheus, "scrape", lambda url, **kw: prometheus.parse(_TRITON_PROM_TEXT)
    )

    metrics_list, state = scrape_triton("http://fake:8002/metrics", None, 30.0)

    assert len(metrics_list) == 2
    llama = next(m for m in metrics_list if m.model_name == "llama")
    assert llama.triton_requests_success_per_sec is None
    assert llama.triton_avg_request_latency_us is None
    assert llama.triton_queue_depth == 3


def test_second_scrape_computes_rates(monkeypatch):
    """Second scrape with prev_state should compute non-None rates."""
    from l9gpu.monitoring import prometheus

    monkeypatch.setattr(
        prometheus, "scrape", lambda url, **kw: prometheus.parse(_TRITON_PROM_TEXT)
    )

    prev = _make_prev_state()
    metrics_list, state = scrape_triton("http://fake:8002/metrics", prev, 30.0)

    llama = next(m for m in metrics_list if m.model_name == "llama")

    # llama: (1000-900)/30 = 3.33 req/s
    assert llama.triton_requests_success_per_sec is not None
    assert abs(llama.triton_requests_success_per_sec - 100.0 / 30.0) < 0.01

    # llama: (5-4)/30 = 0.033 failures/s
    assert llama.triton_requests_failed_per_sec is not None
    assert abs(llama.triton_requests_failed_per_sec - 1.0 / 30.0) < 0.01

    # avg latency: (5000000-4500000) / (1000-900) = 5000 us
    assert llama.triton_avg_request_latency_us is not None
    assert abs(llama.triton_avg_request_latency_us - 5000.0) < 1.0

    # avg batch size: (1000-900)/(200-180) = 100/20 = 5.0
    assert llama.triton_avg_batch_size is not None
    assert abs(llama.triton_avg_batch_size - 5.0) < 0.01


def test_multi_model_separation(monkeypatch):
    """Each (model, version) pair produces a separate TritonMetrics instance."""
    from l9gpu.monitoring import prometheus

    monkeypatch.setattr(
        prometheus, "scrape", lambda url, **kw: prometheus.parse(_TRITON_PROM_TEXT)
    )

    metrics_list, _ = scrape_triton("http://fake:8002/metrics", None, 30.0)
    models = {m.model_name for m in metrics_list}
    assert models == {"llama", "mistral"}


def test_scrape_failure_returns_empty(monkeypatch):
    """If scrape fails, return empty list and preserve prev_state."""
    from l9gpu.monitoring import prometheus

    monkeypatch.setattr(
        prometheus,
        "scrape",
        lambda url, **kw: (_ for _ in ()).throw(ConnectionError("down")),
    )

    prev = _make_prev_state()
    metrics_list, state = scrape_triton("http://fake:8002/metrics", prev, 30.0)
    assert metrics_list == []
    assert state == prev


def test_queue_depth_gauge(monkeypatch):
    """Queue depth should be an instantaneous gauge, available on first scrape."""
    from l9gpu.monitoring import prometheus

    monkeypatch.setattr(
        prometheus, "scrape", lambda url, **kw: prometheus.parse(_TRITON_PROM_TEXT)
    )

    metrics_list, _ = scrape_triton("http://fake:8002/metrics", None, 30.0)
    mistral = next(m for m in metrics_list if m.model_name == "mistral")
    assert mistral.triton_queue_depth == 0
