# Copyright (c) Last9, Inc.
"""Schema for GPU cost and carbon metrics."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class GPUCostMetrics:
    """Per-GPU cost attribution and energy efficiency metrics.

    Derived by combining GPU hardware metrics (power draw, utilization)
    with cloud instance pricing and optional inference throughput data.
    """

    # GPU identity (data-point attributes)
    gpu_index: Optional[int] = None

    # --- Cost rates ---
    # On-demand price per GPU per hour (USD)
    cost_per_gpu_hour: Optional[float] = None
    # Instantaneous cost rate (USD/s = cost_per_gpu_hour / 3600)
    cost_rate_per_sec: Optional[float] = None

    # --- Inference cost (populated only when vLLM/SGLang endpoint is provided) ---
    # Cost per prompt/input token (USD)
    cost_per_prompt_token: Optional[float] = None
    # Cost per generated/output token (USD)
    cost_per_generation_token: Optional[float] = None

    # --- Energy efficiency ---
    # Generated tokens per watt (higher = better)
    tokens_per_watt: Optional[float] = None
    # Energy per generated token in joules (lower = better)
    joules_per_token: Optional[float] = None

    # --- Idle tracking ---
    # 1 when gpu_util < idle_threshold (0.05 by default)
    is_idle: Optional[int] = None
    # Cost rate when idle; 0.0 when active (tracks waste)
    idle_cost_rate_per_sec: Optional[float] = None

    # --- Carbon / energy ---
    # Grid carbon intensity used for calculation (gCO2/kWh)
    co2_grams_per_kwh: Optional[float] = None
    # Instantaneous CO2 emission rate (g/s)
    co2_rate_grams_per_sec: Optional[float] = None
