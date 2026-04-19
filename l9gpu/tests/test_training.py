# Copyright (c) Last9, Inc.
"""Unit tests for the l9gpu distributed training observability library."""

import time
import pytest
from l9gpu.training.mfu import compute_mfu, compute_tflops, get_peak_tflops
from l9gpu.training.hooks import GradientTracker, DataLoaderTimer, CheckpointTimer

# --- MFU tests ---


def test_mfu_7b_model():
    """Llama-7B style: 7B params, 4096 tokens/step, 8 H100s, 1s step time."""
    mfu = compute_mfu(
        num_params=7_000_000_000,
        tokens_per_step=4096,
        step_time_seconds=1.0,
        gpu_count=8,
        peak_tflops_per_gpu=989.0,
    )
    # 6 × 7e9 × 4096 / 1.0 / 1e12 = 172.0 TFLOPS observed
    # 8 × 989 = 7912 TFLOPS peak
    # MFU = 172/7912 ≈ 0.0217
    assert 0.01 < mfu < 0.10


def test_mfu_with_gradient_checkpointing():
    mfu_no_ckpt = compute_mfu(7e9, 4096, 1.0, 8, 989.0, gradient_checkpointing=False)
    mfu_ckpt = compute_mfu(7e9, 4096, 1.0, 8, 989.0, gradient_checkpointing=True)
    # With checkpointing: 4/3 more FLOPs → higher MFU for same step time
    assert mfu_ckpt > mfu_no_ckpt
    assert abs(mfu_ckpt / mfu_no_ckpt - 4.0 / 3.0) < 0.01


def test_compute_tflops():
    tflops = compute_tflops(7e9, 4096, 1.0)
    # 6 × 7e9 × 4096 / 1.0 / 1e12 ≈ 172
    assert abs(tflops - 172.032) < 1.0


def test_get_peak_tflops():
    assert get_peak_tflops("NVIDIA H100 SXM5 80GB") == 989.0
    assert get_peak_tflops("NVIDIA A100 SXM4 80GB") == 312.0
    assert get_peak_tflops("Unknown GPU") is None


# --- GradientTracker tests ---


class FakeParam:
    """Minimal stand-in for torch.nn.Parameter."""

    def __init__(self, grad_norm=1.0, is_nan=False):
        self.grad = FakeGrad(grad_norm, is_nan)


class FakeGrad:
    def __init__(self, norm_val, is_nan):
        self.data = FakeTensor(norm_val, is_nan)


class FakeTensor:
    def __init__(self, norm_val, is_nan):
        self._norm = float("nan") if is_nan else norm_val

    def norm(self, p):
        return FakeScalar(self._norm)


class FakeScalar:
    def __init__(self, val):
        self._val = val

    def item(self):
        return self._val

    def __pow__(self, other):
        return self._val**other


class FakeModel:
    def __init__(self, params):
        self._params = params

    def parameters(self):
        return self._params


def test_gradient_tracker_normal():
    tracker = GradientTracker()
    model = FakeModel([FakeParam(3.0), FakeParam(4.0)])
    tracker.record_step(model, max_norm=10.0)

    assert tracker.gradient_norm == pytest.approx(5.0)  # sqrt(9+16) = 5
    assert tracker.gradient_nan_count == 0
    assert tracker.gradient_clip_rate == 0.0


def test_gradient_tracker_nan():
    tracker = GradientTracker()
    model = FakeModel([FakeParam(is_nan=True), FakeParam(3.0)])
    tracker.record_step(model)

    assert tracker.gradient_nan_count == 1


def test_gradient_clip_rate():
    tracker = GradientTracker()
    model = FakeModel([FakeParam(10.0)])
    tracker.record_step(model, max_norm=5.0)  # clipped
    tracker.record_step(model, max_norm=15.0)  # not clipped

    assert tracker.gradient_clip_rate == 0.5


# --- CheckpointTimer tests ---


def test_checkpoint_save_timer():
    timer = CheckpointTimer()
    with timer.time_save(checkpoint_size_bytes=1_000_000):
        time.sleep(0.01)

    assert timer.last_save_duration is not None
    assert timer.last_save_duration > 0
    assert timer.last_save_bandwidth is not None
    assert timer.last_save_bandwidth > 0


def test_checkpoint_restore_timer():
    timer = CheckpointTimer()
    with timer.time_restore():
        time.sleep(0.01)

    assert timer.last_restore_duration is not None
    assert timer.last_restore_duration > 0


# --- DataLoaderTimer tests ---


def test_dataloader_timer():
    data = [1, 2, 3]
    timer = DataLoaderTimer(data)

    results = []
    for batch in timer:
        results.append(batch)

    assert results == [1, 2, 3]
    assert timer.last_wait_seconds is not None
    assert len(timer) == 3
