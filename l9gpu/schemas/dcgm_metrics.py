# Copyright (c) Last9, Inc.
"""Schema for DCGM profiling metrics scraped from dcgm-exporter."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class DcgmProfilingMetrics:
    """Per-GPU DCGM profiling metrics.

    Populated by scraping the dcgm-exporter Prometheus endpoint
    (default: http://localhost:9400/metrics).

    All ratio fields are fractions in [0.0, 1.0] (not percentages).
    """

    gpu_index: Optional[int] = None  # gpu.index  (data-point attribute)
    gpu_uuid: Optional[str] = None  # gpu.uuid   (data-point attribute)
    gpu_model: Optional[str] = None  # gpu.model  (data-point attribute)

    # DCGM_FI_PROF_SM_ACTIVE — fraction of time at least one warp is active on an SM
    sm_active: Optional[float] = None

    # DCGM_FI_PROF_DRAM_ACTIVE — fraction of time DRAM interface is active
    dram_active: Optional[float] = None

    # DCGM_FI_PROF_GR_ENGINE_ACTIVE — fraction of time the graphics engine is active
    gr_engine_active: Optional[float] = None

    # DCGM_FI_PROF_PIPE_TENSOR_ACTIVE — fraction of cycles tensor cores are executing
    tensor_active: Optional[float] = None

    # DCGM_FI_PROF_PIPE_FP64_ACTIVE — fraction of cycles FP64 pipes are active
    fp64_active: Optional[float] = None

    # DCGM_FI_PROF_PIPE_FP32_ACTIVE — fraction of cycles FP32 pipes are active
    fp32_active: Optional[float] = None

    # DCGM_FI_PROF_PIPE_FP16_ACTIVE — fraction of cycles FP16/BF16 pipes are active
    fp16_active: Optional[float] = None

    # --- Phase 6: advanced profiling gauges ---

    # DCGM_FI_PROF_SM_OCCUPANCY — warp residency on SM vs. theoretical maximum
    sm_occupancy: Optional[float] = None

    # DCGM_FI_PROF_NVLINK_TX_BYTES — NVLink transmit throughput (bytes/sec gauge)
    # Always 0 on GPUs without NVLink (T4, A10G); non-zero on A100/H100 SXM.
    nvlink_tx_bytes: Optional[float] = None

    # DCGM_FI_PROF_NVLINK_RX_BYTES — NVLink receive throughput (bytes/sec gauge)
    nvlink_rx_bytes: Optional[float] = None

    # DCGM_FI_PROF_PCIE_TX_BYTES — PCIe transmit throughput (bytes/sec gauge)
    # Supersedes deprecated DCGM_FI_DEV_PCIE_TX_THROUGHPUT.
    prof_pcie_tx_bytes: Optional[float] = None

    # DCGM_FI_PROF_PCIE_RX_BYTES — PCIe receive throughput (bytes/sec gauge)
    prof_pcie_rx_bytes: Optional[float] = None

    # --- MIG support ---

    # True when the GPU has MIG mode enabled.
    # On MIG-enabled GPUs, DCGM_FI_DEV_GPU_UTIL returns 0;
    # use gr_engine_active as utilization instead.
    mig_enabled: Optional[bool] = None

    # MIG GPU Instance ID (e.g. "1", "3").  None on non-MIG GPUs.
    mig_instance_id: Optional[str] = None
