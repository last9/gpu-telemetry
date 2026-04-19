# Copyright (c) Last9, Inc.
"""Model FLOPs Utilization (MFU) calculator for transformer LLMs.

MFU = observed_tflops / theoretical_peak_tflops
    = (6 × N × T) / (step_time × GPU_count × peak_TFLOPS_per_GPU)

Where:
  N = number of model parameters
  T = number of tokens per step (batch_size × seq_len)
  6 = multiply-add operations per parameter per token
      (2 FLOPs per MAC × 3 for fwd+bwd with gradient checkpointing)

References:
  PaLM paper (Chowdhery et al., 2022) — introduced MFU
  MegaScale (ByteDance, 2024) — 55.2% MFU on 12,288 GPUs
  Llama 3.1 report — 38-43% MFU
"""

from typing import Optional

# NVIDIA GPU peak TFLOPS for BF16/FP16 (Tensor Cores, sparse off)
# Source: NVIDIA product pages, March 2026
GPU_PEAK_TFLOPS: dict = {
    # Hopper
    "H100 SXM5": 989.0,
    "H100 PCIe": 756.0,
    "H200 SXM5": 989.0,
    # Ada Lovelace
    "L4": 242.0,
    "L40S": 733.0,
    # Ampere
    "A100 SXM4 40GB": 312.0,
    "A100 SXM4 80GB": 312.0,
    "A100 PCIe 40GB": 312.0,
    "A10G": 125.0,
    "A10": 125.0,
    # Blackwell
    "B200 SXM6": 4500.0,
    # Turing / Volta
    "T4": 65.0,
    "V100 SXM2": 125.0,
}


def get_peak_tflops(gpu_model: str) -> Optional[float]:
    """Return peak BF16 TFLOPS for a GPU model string.

    Matches by substring so "NVIDIA H100 SXM5 80GB" → 989.0.
    Returns None if the model is not in the table.
    """
    for key, tflops in GPU_PEAK_TFLOPS.items():
        if key.lower() in gpu_model.lower():
            return tflops
    return None


def compute_mfu(
    num_params: int,
    tokens_per_step: int,
    step_time_seconds: float,
    gpu_count: int,
    peak_tflops_per_gpu: float,
    gradient_checkpointing: bool = False,
) -> float:
    """Compute Model FLOPs Utilization.

    Args:
        num_params: Total trainable parameter count.
        tokens_per_step: batch_size × sequence_length.
        step_time_seconds: Wall-clock time for one training step (s).
        gpu_count: Number of GPUs in the training job.
        peak_tflops_per_gpu: Theoretical peak TFLOPS per GPU.
        gradient_checkpointing: If True, multiply by 4/3 (recomputation overhead).

    Returns:
        MFU in range [0, 1]; values > 1 indicate measurement errors.
    """
    # 6 FLOPs per parameter per token (fwd + bwd with reuse)
    flops_per_step = 6 * num_params * tokens_per_step
    if gradient_checkpointing:
        # Recomputation adds ~1/3 more FLOPs in the backward pass
        flops_per_step = int(flops_per_step * (4 / 3))

    observed_tflops = flops_per_step / step_time_seconds / 1e12
    theoretical_peak = gpu_count * peak_tflops_per_gpu

    return observed_tflops / theoretical_peak if theoretical_peak > 0 else 0.0


def compute_tflops(
    num_params: int,
    tokens_per_step: int,
    step_time_seconds: float,
    gradient_checkpointing: bool = False,
) -> float:
    """Compute achieved TFLOPS (not normalized by peak)."""
    flops_per_step = 6 * num_params * tokens_per_step
    if gradient_checkpointing:
        flops_per_step = int(flops_per_step * (4 / 3))
    return flops_per_step / step_time_seconds / 1e12
