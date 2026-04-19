# Copyright (c) Last9, Inc.
"""DCGM profiling metrics collector.

Scrapes the dcgm-exporter Prometheus endpoint and returns per-GPU
DcgmProfilingMetrics instances ready to be emitted via any l9gpu sink.
"""

import logging
from typing import Dict, List, Optional

from l9gpu.monitoring import prometheus
from l9gpu.schemas.dcgm_metrics import DcgmProfilingMetrics

logger = logging.getLogger(__name__)

# Mapping: Prometheus metric name → DcgmProfilingMetrics field name
_DCGM_FIELD_MAP = {
    "DCGM_FI_PROF_SM_ACTIVE": "sm_active",
    "DCGM_FI_PROF_DRAM_ACTIVE": "dram_active",
    "DCGM_FI_PROF_GR_ENGINE_ACTIVE": "gr_engine_active",
    "DCGM_FI_PROF_PIPE_TENSOR_ACTIVE": "tensor_active",
    "DCGM_FI_PROF_PIPE_FP64_ACTIVE": "fp64_active",
    "DCGM_FI_PROF_PIPE_FP32_ACTIVE": "fp32_active",
    "DCGM_FI_PROF_PIPE_FP16_ACTIVE": "fp16_active",
    # Phase 6 — advanced profiling gauges (all report bytes/sec or fractions)
    "DCGM_FI_PROF_SM_OCCUPANCY": "sm_occupancy",
    "DCGM_FI_PROF_NVLINK_TX_BYTES": "nvlink_tx_bytes",
    "DCGM_FI_PROF_NVLINK_RX_BYTES": "nvlink_rx_bytes",
    "DCGM_FI_PROF_PCIE_TX_BYTES": "prof_pcie_tx_bytes",
    "DCGM_FI_PROF_PCIE_RX_BYTES": "prof_pcie_rx_bytes",
}


def scrape_dcgm(endpoint: str) -> List[DcgmProfilingMetrics]:
    """Scrape dcgm-exporter and return one DcgmProfilingMetrics per GPU.

    dcgm-exporter labels use ``gpu`` (index string), ``UUID``, and
    ``modelName`` for GPU identity.
    """
    try:
        samples = prometheus.scrape(endpoint)
    except Exception as exc:
        logger.error("Failed to scrape DCGM endpoint %s: %s", endpoint, exc)
        return []

    # Collect per-GPU field values, UUID, model name, and MIG instance ID
    gpu_fields: Dict[str, Dict[str, float]] = {}
    gpu_uuid: Dict[str, str] = {}
    gpu_model: Dict[str, str] = {}
    gpu_mig_instance: Dict[str, Optional[str]] = {}

    for dcgm_name, field_name in _DCGM_FIELD_MAP.items():
        for labels, value in samples.get(dcgm_name, []):
            gpu_idx = labels.get("gpu", "0")
            gpu_fields.setdefault(gpu_idx, {})[field_name] = value
            if "UUID" in labels:
                gpu_uuid[gpu_idx] = labels["UUID"]
            if "modelName" in labels:
                gpu_model[gpu_idx] = labels["modelName"]
            # dcgm-exporter adds a "GPU_I_ID" or "gpu_instance_id" label
            # when MIG is enabled.
            mig_id = labels.get("GPU_I_ID") or labels.get("gpu_instance_id")
            if mig_id is not None:
                gpu_mig_instance[gpu_idx] = mig_id

    result: List[DcgmProfilingMetrics] = []
    for gpu_idx, field_values in gpu_fields.items():
        try:
            idx_int: Optional[int] = int(gpu_idx)
        except ValueError:
            idx_int = None

        mig_id = gpu_mig_instance.get(gpu_idx)
        metrics = DcgmProfilingMetrics(
            gpu_index=idx_int,
            gpu_uuid=gpu_uuid.get(gpu_idx),
            gpu_model=gpu_model.get(gpu_idx),
            mig_enabled=mig_id is not None,
            mig_instance_id=mig_id,
            **field_values,
        )
        result.append(metrics)

    return result
