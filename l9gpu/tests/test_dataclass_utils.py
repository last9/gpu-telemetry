# Copyright (c) Last9, Inc.
"""Tests for l9gpu.monitoring.dataclass_utils.max_fields."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from l9gpu.monitoring.dataclass_utils import max_fields


@dataclass
class _Scalars:
    temperature: Optional[int] = None
    power: Optional[float] = None


@dataclass
class _WithDict:
    ecc_per_block: Optional[Dict[str, int]] = None


@dataclass
class _WithList:
    link_bandwidth: Optional[List[int]] = field(default=None)


class TestMaxFieldsScalars:
    def test_both_present(self) -> None:
        op = max_fields(_Scalars)
        result = op(
            _Scalars(temperature=80, power=1.2), _Scalars(temperature=85, power=0.9)
        )
        assert result == _Scalars(temperature=85, power=1.2)

    def test_left_none_uses_right(self) -> None:
        op = max_fields(_Scalars)
        result = op(
            _Scalars(temperature=None, power=1.2), _Scalars(temperature=85, power=None)
        )
        assert result == _Scalars(temperature=85, power=1.2)


class TestMaxFieldsDict:
    def test_per_key_max_on_overlap(self) -> None:
        op = max_fields(_WithDict)
        left = _WithDict(ecc_per_block={"umc0": 5, "umc1": 2})
        right = _WithDict(ecc_per_block={"umc0": 3, "umc1": 7, "umc2": 1})
        result = op(left, right)
        assert result.ecc_per_block == {"umc0": 5, "umc1": 7, "umc2": 1}


class TestMaxFieldsList:
    def test_element_wise_max_same_length(self) -> None:
        # Ensures per-link peaks aren't lost to lexicographic comparison.
        op = max_fields(_WithList)
        left = _WithList(link_bandwidth=[100, 50, 30])
        right = _WithList(link_bandwidth=[80, 90, 60])
        result = op(left, right)
        assert result.link_bandwidth == [100, 90, 60]

    def test_element_wise_handles_none_entries(self) -> None:
        op = max_fields(_WithList)
        left = _WithList(link_bandwidth=[100, None, 30])  # type: ignore[list-item]
        right = _WithList(link_bandwidth=[80, 90, None])  # type: ignore[list-item]
        result = op(left, right)
        assert result.link_bandwidth == [100, 90, 30]

    def test_length_mismatch_falls_back_to_right(self) -> None:
        op = max_fields(_WithList)
        left = _WithList(link_bandwidth=[100, 50])
        right = _WithList(link_bandwidth=[80, 90, 60])
        result = op(left, right)
        assert result.link_bandwidth == [80, 90, 60]
