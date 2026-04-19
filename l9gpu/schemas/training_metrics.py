# Copyright (c) Last9, Inc.
"""Schema for distributed training observability metrics."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class TrainingMetrics:
    """Per-training-step metrics emitted by L9GPUTrainingMonitor.

    Collected via PyTorch hooks attached to the model, optimizer,
    and DataLoader. Exported via OTLP to any l9gpu-compatible backend.
    """

    # --- Compute efficiency ---
    # Model FLOPs Utilization: observed_tflops / theoretical_peak_tflops
    # Reference: LLMs typically achieve 35-55% MFU in production
    mfu: Optional[float] = None

    # Achieved TFLOPS (observed forward+backward FLOPs / step_time)
    tflops: Optional[float] = None

    # Wall-clock time per training step (seconds)
    step_time: Optional[float] = None

    # --- Gradient health ---
    # L2 norm of all gradients (upward trend = instability)
    gradient_norm: Optional[float] = None

    # Number of parameters with NaN or Inf gradients (should always be 0)
    gradient_nan_count: Optional[int] = None

    # Fraction of steps where gradient clipping was applied (high = learning rate too large)
    gradient_clip_rate: Optional[float] = None

    # --- Loss ---
    training_loss: Optional[float] = None

    # --- DataLoader ---
    # Time blocked waiting on next(dataloader) per step (seconds)
    # High values = DataLoader is the bottleneck, not GPU
    dataloader_wait: Optional[float] = None

    # --- Checkpoint I/O ---
    # Time to save a checkpoint (seconds)
    checkpoint_save_duration: Optional[float] = None
    # Checkpoint save throughput (bytes/s)
    checkpoint_save_bandwidth: Optional[float] = None
    # Time to restore from checkpoint (seconds)
    checkpoint_restore_duration: Optional[float] = None
