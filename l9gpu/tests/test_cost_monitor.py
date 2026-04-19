# Copyright (c) Last9, Inc.
"""Unit tests for GPU cost and carbon analytics."""

import pytest
from l9gpu.monitoring.cost_monitor import compute_cost_metrics, get_cost_per_gpu_hour


def test_cost_per_gpu_hour_lookup():
    assert get_cost_per_gpu_hour("g6.xlarge") == pytest.approx(0.805)
    assert get_cost_per_gpu_hour("g5.xlarge") == pytest.approx(1.006)
    assert get_cost_per_gpu_hour("p5.48xlarge") == pytest.approx(55.04 / 8, rel=0.01)
    assert get_cost_per_gpu_hour("unknown.instance") is None


def test_basic_cost_metrics():
    m = compute_cost_metrics(
        gpu_index=0,
        power_draw_watts=300.0,
        gpu_util=0.8,
        prompt_tokens_per_sec=100.0,
        generation_tokens_per_sec=50.0,
        cost_per_gpu_hour=6.88,
    )
    assert m.cost_per_gpu_hour == 6.88
    assert m.cost_rate_per_sec == pytest.approx(6.88 / 3600.0)
    assert m.cost_per_prompt_token is not None
    assert m.cost_per_generation_token is not None
    assert m.tokens_per_watt == pytest.approx(150.0 / 300.0)
    assert m.joules_per_token == pytest.approx(300.0 / 150.0)
    assert m.is_idle == 0


def test_idle_detection():
    m = compute_cost_metrics(
        gpu_index=0,
        power_draw_watts=50.0,
        gpu_util=0.02,
        prompt_tokens_per_sec=None,
        generation_tokens_per_sec=None,
        cost_per_gpu_hour=0.805,
        idle_threshold=0.05,
    )
    assert m.is_idle == 1
    assert m.idle_cost_rate_per_sec == pytest.approx(0.805 / 3600.0)


def test_no_inference_tokens():
    m = compute_cost_metrics(
        gpu_index=0,
        power_draw_watts=300.0,
        gpu_util=0.5,
        prompt_tokens_per_sec=None,
        generation_tokens_per_sec=None,
        cost_per_gpu_hour=6.88,
    )
    assert m.cost_per_prompt_token is None
    assert m.cost_per_generation_token is None
    assert m.tokens_per_watt is None


def test_carbon_calculation():
    m = compute_cost_metrics(
        gpu_index=0,
        power_draw_watts=300.0,
        gpu_util=0.5,
        prompt_tokens_per_sec=None,
        generation_tokens_per_sec=None,
        cost_per_gpu_hour=6.88,
        co2_grams_per_kwh=475.0,
        pue=1.2,
    )
    assert m.co2_grams_per_kwh == 475.0
    # CO2 rate = 300W × 1.2 / 1000 × 475 / 3600 = 0.0475 g/s
    assert m.co2_rate_grams_per_sec == pytest.approx(
        300.0 * 1.2 / 1000.0 * 475.0 / 3600.0, rel=0.01
    )


def test_no_carbon_when_not_configured():
    m = compute_cost_metrics(
        gpu_index=0,
        power_draw_watts=300.0,
        gpu_util=0.5,
        prompt_tokens_per_sec=None,
        generation_tokens_per_sec=None,
        cost_per_gpu_hour=6.88,
    )
    assert m.co2_rate_grams_per_sec is None
