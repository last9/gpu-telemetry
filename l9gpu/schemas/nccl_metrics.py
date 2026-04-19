# Copyright (c) Last9, Inc.
"""Schema for NCCL collective communication metrics.

Populated by parsing NCCL Inspector JSON logs (LD_PRELOAD approach).
NCCL Inspector is production-ready as of NCCL 2.26+ (NVIDIA, 2025).
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class NCCLCollectiveMetrics:
    """Per-collective-type NCCL communication metrics.

    One instance per (collective_type, rank) combination per flush interval.
    """

    # Collective type (AllReduce, AllGather, ReduceScatter, Broadcast, Send, Recv)
    collective_type: Optional[str] = None

    # Rank this observation came from
    rank: Optional[int] = None

    # Message size (bytes)
    message_size_bytes: Optional[float] = None

    # Algorithmic bandwidth (bytes/s) — theoretical for the collective algorithm
    bandwidth_bytes_per_sec: Optional[float] = None

    # Bus bandwidth (bytes/s) — actual achieved on the interconnect
    bus_bandwidth_bytes_per_sec: Optional[float] = None

    # Collective execution duration (microseconds)
    duration_us: Optional[float] = None

    # 1 if this rank was a straggler (>straggler_threshold_ms behind median)
    is_straggler: Optional[int] = None
