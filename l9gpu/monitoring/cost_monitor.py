# Copyright (c) Last9, Inc.
"""GPU cost and carbon analytics.

Combines GPU hardware metrics (power, utilization) with cloud pricing
and optional inference throughput to compute cost/token, tokens/watt,
and carbon emission rate metrics.

Pricing table reflects AWS on-demand us-east-1 rates as of March 2026
(post June-2025 price cuts). Override with --cost-per-gpu-hour or
--instance-type for accuracy on other clouds/regions.
"""

import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# AWS on-demand per-GPU-hour prices (us-east-1, March 2026)
# Source: instances.vantage.sh, verified March 2026
INSTANCE_GPU_COST_USD_PER_HR: dict = {
    # NVIDIA H100 SXM
    "p5.48xlarge": 55.04 / 8,  # $6.88/GPU
    # NVIDIA A100 40GB
    "p4d.24xlarge": 21.96 / 8,  # $2.745/GPU
    # NVIDIA A100 80GB
    "p4de.24xlarge": 40.96 / 8,  # $5.12/GPU
    # NVIDIA L40S 48GB
    "g6e.xlarge": 2.56,
    "g6e.2xlarge": 3.83,
    "g6e.4xlarge": 5.49,
    "g6e.8xlarge": 10.27,
    "g6e.12xlarge": 16.31,
    "g6e.48xlarge": 65.25 / 8,
    # NVIDIA L4 24GB
    "g6.xlarge": 0.805,
    "g6.2xlarge": 1.32,
    "g6.4xlarge": 2.42,
    "g6.8xlarge": 4.36,
    "g6.12xlarge": 7.00,
    "g6.48xlarge": 27.81 / 8,
    # NVIDIA A10G 24GB
    "g5.xlarge": 1.006,
    "g5.2xlarge": 1.212,
    "g5.4xlarge": 1.624,
    "g5.8xlarge": 2.448,
    "g5.12xlarge": 5.672 / 4,
    "g5.48xlarge": 16.288 / 8,
    # NVIDIA T4 16GB
    "g4dn.xlarge": 0.526,
    "g4dn.2xlarge": 0.752,
    "g4dn.4xlarge": 1.204,
    "g4dn.8xlarge": 2.264,
    "g4dn.12xlarge": 3.912 / 4,
    "g4dn.16xlarge": 4.528,
    "g4dn.metal": 7.824 / 8,
    # Intel Gaudi 2
    "dl1.24xlarge": 13.11 / 8,
}


def detect_instance_type() -> Optional[str]:
    """Try EC2 IMDSv2 to get the current instance type.

    Returns None when not running on EC2 or if the request fails.
    """
    try:
        # Step 1: get IMDSv2 token
        token_resp = requests.put(
            "http://169.254.169.254/latest/api/token",
            headers={"X-aws-ec2-metadata-token-ttl-seconds": "60"},
            timeout=2,
        )
        token_resp.raise_for_status()
        token = token_resp.text.strip()

        # Step 2: use token to read instance type
        meta_resp = requests.get(
            "http://169.254.169.254/latest/meta-data/instance-type",
            headers={"X-aws-ec2-metadata-token": token},
            timeout=2,
        )
        meta_resp.raise_for_status()
        return meta_resp.text.strip()
    except Exception:
        return None


def get_cost_per_gpu_hour(instance_type: str) -> Optional[float]:
    """Look up the on-demand per-GPU cost for the given instance type."""
    return INSTANCE_GPU_COST_USD_PER_HR.get(instance_type)


def compute_cost_metrics(
    gpu_index: int,
    *,
    power_draw_watts: Optional[float],
    gpu_util: Optional[float],
    prompt_tokens_per_sec: Optional[float],
    generation_tokens_per_sec: Optional[float],
    cost_per_gpu_hour: float,
    idle_threshold: float = 0.05,
    co2_grams_per_kwh: Optional[float] = None,
    pue: float = 1.0,
) -> "GPUCostMetrics":  # noqa: F821
    """Compute GPUCostMetrics from hardware + inference data.

    Args:
        gpu_index: GPU ordinal.
        power_draw_watts: Current GPU power draw (W).
        gpu_util: GPU compute utilization fraction (0–1).
        prompt_tokens_per_sec: Input token throughput (tokens/s).
        generation_tokens_per_sec: Output token throughput (tokens/s).
        cost_per_gpu_hour: On-demand USD/GPU/hr.
        idle_threshold: Utilization fraction below which GPU is "idle".
        co2_grams_per_kwh: Grid carbon intensity (g CO2 / kWh).
        pue: Power Usage Effectiveness multiplier (1.0 = no overhead).
    """
    from l9gpu.schemas.cost_metrics import GPUCostMetrics

    cost_rate = cost_per_gpu_hour / 3600.0

    # Inference cost per token
    cpt_prompt: Optional[float] = None
    cpt_gen: Optional[float] = None
    if prompt_tokens_per_sec and prompt_tokens_per_sec > 0:
        cpt_prompt = cost_rate / prompt_tokens_per_sec
    if generation_tokens_per_sec and generation_tokens_per_sec > 0:
        cpt_gen = cost_rate / generation_tokens_per_sec

    # Energy efficiency
    total_tps = (prompt_tokens_per_sec or 0.0) + (generation_tokens_per_sec or 0.0)
    tpw: Optional[float] = None
    jpt: Optional[float] = None
    if power_draw_watts and power_draw_watts > 0 and total_tps > 0:
        tpw = total_tps / power_draw_watts
        jpt = power_draw_watts / total_tps

    # Idle
    is_idle = 0
    if gpu_util is not None and gpu_util < idle_threshold:
        is_idle = 1

    # Carbon
    co2_rate: Optional[float] = None
    if co2_grams_per_kwh is not None and power_draw_watts is not None:
        # g/s = W × pue / 1000 × gCO2/kWh / 3600
        co2_rate = (power_draw_watts * pue / 1000.0) * co2_grams_per_kwh / 3600.0

    return GPUCostMetrics(
        gpu_index=gpu_index,
        cost_per_gpu_hour=cost_per_gpu_hour,
        cost_rate_per_sec=cost_rate,
        cost_per_prompt_token=cpt_prompt,
        cost_per_generation_token=cpt_gen,
        tokens_per_watt=tpw,
        joules_per_token=jpt,
        is_idle=is_idle,
        idle_cost_rate_per_sec=cost_rate if is_idle else 0.0,
        co2_grams_per_kwh=co2_grams_per_kwh,
        co2_rate_grams_per_sec=co2_rate,
    )
