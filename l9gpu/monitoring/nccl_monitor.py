# Copyright (c) Last9, Inc.
"""NCCL Inspector log parser for collective communication observability.

Architecture:
  - NCCL Inspector runs as LD_PRELOAD=libnccl_inspector.so alongside training
  - It writes structured JSON lines to a log file (configurable via NCCL_INSPECTOR_LOG)
  - This module tails that file, parses records, and emits NCCLCollectiveMetrics

NCCL Inspector is production-ready since NCCL 2.26 (NVIDIA blog, 2025).
Enable with: LD_PRELOAD=/path/to/libnccl_inspector.so NCCL_INSPECTOR_LOG=/tmp/nccl.jsonl

Reference:
  https://developer.nvidia.com/blog/enhancing-communication-observability-of-ai-workloads-with-nccl-inspector
"""

import json
import logging
import os
import statistics
from typing import Dict, List, Optional, Tuple

from l9gpu.schemas.nccl_metrics import NCCLCollectiveMetrics

logger = logging.getLogger(__name__)


def _parse_record(obj: dict) -> Optional[NCCLCollectiveMetrics]:
    """Parse one NCCL Inspector JSON record into NCCLCollectiveMetrics."""
    try:
        return NCCLCollectiveMetrics(
            collective_type=obj.get("collective") or obj.get("type"),
            rank=obj.get("rank"),
            message_size_bytes=float(obj["size"]) if "size" in obj else None,
            bandwidth_bytes_per_sec=(
                float(obj["alg_bw"]) * 1e9 if "alg_bw" in obj else None
            ),
            bus_bandwidth_bytes_per_sec=(
                float(obj["bus_bw"]) * 1e9 if "bus_bw" in obj else None
            ),
            duration_us=(
                float(obj["time_us"])
                if "time_us" in obj
                else (float(obj["time_ms"]) * 1000 if "time_ms" in obj else None)
            ),
        )
    except (KeyError, ValueError, TypeError) as exc:
        logger.debug("Skipping NCCL record: %s — %s", exc, obj)
        return None


def tail_and_parse(
    log_path: str,
    file_position: int,
    straggler_threshold_ms: float = 1000.0,
) -> Tuple[List[NCCLCollectiveMetrics], int]:
    """Read new lines from the NCCL Inspector log file since last position.

    Returns (metrics_list, new_file_position).
    Detects stragglers: any rank whose duration > median + straggler_threshold_ms.
    """
    if not os.path.exists(log_path):
        return [], file_position

    records: List[NCCLCollectiveMetrics] = []
    try:
        with open(log_path, "r") as fh:
            fh.seek(file_position)
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    m = _parse_record(obj)
                    if m is not None:
                        records.append(m)
                except json.JSONDecodeError:
                    continue
            new_position = fh.tell()
    except OSError as exc:
        logger.error("Cannot read NCCL log %s: %s", log_path, exc)
        return [], file_position

    if not records:
        return [], new_position

    # Straggler detection: group by collective_type, find outlier ranks
    durations_by_type: Dict[str, List[Tuple[int, float]]] = {}
    for m in records:
        if m.collective_type and m.rank is not None and m.duration_us is not None:
            key = m.collective_type
            durations_by_type.setdefault(key, []).append((m.rank, m.duration_us))

    straggler_ranks: Dict[Tuple[str, int], bool] = {}
    threshold_us = straggler_threshold_ms * 1000.0
    for ctype, rank_durations in durations_by_type.items():
        if len(rank_durations) < 2:
            continue
        dur_vals = [d for _, d in rank_durations]
        median_us = statistics.median(dur_vals)
        for rank, dur in rank_durations:
            straggler_ranks[(ctype, rank)] = (dur - median_us) > threshold_us

    # Annotate records
    for m in records:
        if m.collective_type and m.rank is not None:
            is_st = straggler_ranks.get((m.collective_type, m.rank))
            m.is_straggler = 1 if is_st else 0

    return records, new_position
