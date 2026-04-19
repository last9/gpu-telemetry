# Copyright (c) Last9, Inc.
"""Unit tests for NCCL Inspector log parser."""

import json
import os
import tempfile
import pytest
from l9gpu.monitoring.nccl_monitor import tail_and_parse


def _write_log(path, records):
    with open(path, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def test_basic_parse():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        records = [
            {
                "collective": "AllReduce",
                "rank": 0,
                "size": 1048576,
                "alg_bw": 100.5,
                "bus_bw": 80.2,
                "time_us": 1200.0,
            },
            {
                "collective": "AllReduce",
                "rank": 1,
                "size": 1048576,
                "alg_bw": 99.0,
                "bus_bw": 79.5,
                "time_us": 1250.0,
            },
        ]
        _write_log(f.name, records)

    try:
        metrics, pos = tail_and_parse(f.name, 0)
        assert len(metrics) == 2
        assert metrics[0].collective_type == "AllReduce"
        assert metrics[0].rank == 0
        assert metrics[0].message_size_bytes == 1048576
        assert metrics[0].bandwidth_bytes_per_sec == pytest.approx(100.5e9)
        assert pos > 0
    finally:
        os.unlink(f.name)


def test_incremental_read():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        _write_log(
            f.name,
            [
                {"collective": "AllGather", "rank": 0, "size": 512, "time_us": 100.0},
            ],
        )

    try:
        metrics1, pos1 = tail_and_parse(f.name, 0)
        assert len(metrics1) == 1

        # Read again from same position — no new records
        metrics2, pos2 = tail_and_parse(f.name, pos1)
        assert len(metrics2) == 0

        # Append a new record
        with open(f.name, "a") as fh:
            fh.write(
                json.dumps(
                    {"collective": "Broadcast", "rank": 0, "size": 256, "time_us": 50.0}
                )
                + "\n"
            )

        metrics3, pos3 = tail_and_parse(f.name, pos2)
        assert len(metrics3) == 1
        assert metrics3[0].collective_type == "Broadcast"
    finally:
        os.unlink(f.name)


def test_straggler_detection():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        records = [
            {"collective": "AllReduce", "rank": 0, "size": 1024, "time_us": 100.0},
            {"collective": "AllReduce", "rank": 1, "size": 1024, "time_us": 120.0},
            {
                "collective": "AllReduce",
                "rank": 2,
                "size": 1024,
                "time_us": 2500000.0,
            },  # 2.5s straggler
        ]
        _write_log(f.name, records)

    try:
        metrics, _ = tail_and_parse(f.name, 0, straggler_threshold_ms=1000.0)
        rank2 = next(m for m in metrics if m.rank == 2)
        rank0 = next(m for m in metrics if m.rank == 0)
        assert rank2.is_straggler == 1
        assert rank0.is_straggler == 0
    finally:
        os.unlink(f.name)


def test_missing_file():
    metrics, pos = tail_and_parse("/nonexistent/file.jsonl", 0)
    assert metrics == []
    assert pos == 0
