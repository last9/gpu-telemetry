# Copyright (c) Last9, Inc.
"""Lightweight Prometheus text-format scraper and parser.

Used by dcgm_monitor, vllm_monitor, and nim_monitor to scrape Prometheus
endpoints and translate metrics into OTel-ready data.
"""

import re
from typing import Dict, List, Optional, Tuple

import requests

Labels = Dict[str, str]
Sample = Tuple[Labels, float]
# {metric_name: [(labels_dict, value), ...]}
MetricSamples = Dict[str, List[Sample]]


def scrape(url: str, timeout: int = 10) -> MetricSamples:
    """Scrape a Prometheus metrics endpoint and return parsed samples."""
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    return parse(response.text)


def parse(text: str) -> MetricSamples:
    """Parse Prometheus text format into {metric_name: [(labels, value)]}."""
    result: MetricSamples = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # metric_name{label1="v1",...} value [timestamp]
        m = re.match(r"^([a-zA-Z_:][a-zA-Z0-9_:]*)\{([^}]*)\}\s+(\S+)", line)
        if m:
            name, labels_str, value_str = m.group(1), m.group(2), m.group(3)
        else:
            # metric_name value [timestamp]
            m = re.match(r"^([a-zA-Z_:][a-zA-Z0-9_:]*)\s+(\S+)", line)
            if m:
                name, value_str = m.group(1), m.group(2)
                labels_str = ""
            else:
                continue
        try:
            value = float(value_str)
        except ValueError:
            continue
        labels: Labels = {}
        if labels_str:
            for lm in re.finditer(r'(\w+)="([^"]*)"', labels_str):
                labels[lm.group(1)] = lm.group(2)
        result.setdefault(name, []).append((labels, value))
    return result


def histogram_quantile(
    buckets: List[Tuple[float, float]],
    count: float,
    quantile: float,
) -> Optional[float]:
    """Estimate a histogram quantile from (le, cumulative_count) bucket pairs.

    Implements the same linear-interpolation algorithm as Prometheus
    ``histogram_quantile()``.
    """
    if count == 0:
        return None
    finite = sorted((le, c) for le, c in buckets if le != float("inf"))
    if not finite:
        return None
    target = quantile * count
    prev_le, prev_count = 0.0, 0.0
    for le, cum_count in finite:
        if cum_count >= target:
            if cum_count == prev_count:
                return prev_le
            return prev_le + (le - prev_le) * (target - prev_count) / (
                cum_count - prev_count
            )
        prev_le, prev_count = le, cum_count
    # All observations exceed the last finite bucket bound
    return finite[-1][0]
