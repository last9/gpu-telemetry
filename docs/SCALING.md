# Scaling l9gpu: Cardinality Management Guide

## The Problem

GPU telemetry at scale generates high-cardinality metric series:

```
per-GPU metrics × GPUs/node × nodes × per-rank NCCL × per-model inference = millions of series
```

A 1,000-node cluster with 8 GPUs each, running 4 models with tensor parallelism,
produces ~200,000+ unique time series at 15s scrape intervals.

## Mitigation Strategies

### 1. OTel Collector Interval Processor

Enable downsampling in `values.yaml`:

```yaml
otelCollector:
  enabled: true
  intervalSeconds: 60  # aggregate to 1-minute resolution
```

This reduces data volume by 4x (from 15s scrape interval).

### 2. Dimension Pruning

Drop high-cardinality attributes when not needed:

- **`gpu.uuid`**: Unique per GPU; use `gpu.index` within a node (sufficient for dashboards).
  Only keep `gpu.uuid` for fleet-wide deduplication.
- **`gpu.model`**: Same for all GPUs on a node — move to resource attribute, not data-point.
- **`nccl.rank`**: Keep for straggler analysis; drop in production cost-saving mode.

Configure in the OTel Collector `filter/drop_noisy` processor.

### 3. Selective Monitor Deployment

Enable only the monitors you need in Helm:

```yaml
collectors:
  nvidia: true     # always on
  amd: false       # only on AMD nodes
  gaudi: false     # only on Gaudi nodes
  vllm: true       # only on inference nodes
  triton: false
  sglang: false
  tgi: false
fleetHealth:
  enabled: true    # always on (lightweight)
costMonitor:
  enabled: false   # only on nodes where cost tracking matters
```

### 4. Training Metrics Aggregation

`L9GPUTrainingMonitor` emits per-step metrics. For long training runs:
- Set export interval to 30s (default) — this aggregates ~100 steps into one export
- Gradient norm: track only the max per export window
- MFU: track the average per window (stable metric)

### 5. Backend-Side Recording Rules

Pre-aggregate at the backend to reduce query-time cardinality:

```promql
# Per-node GPU utilization average (aggregates away gpu.index)
avg by (host.name) (gpu.utilization)

# Fleet-wide health score histogram
histogram_quantile(0.05, sum by (le) (gpu.health.score))
```

## Cardinality Budget Guidelines

| Deployment Size | Estimated Series | Recommended `intervalSeconds` |
|---|---|---|
| < 100 GPUs | ~10K | 0 (disabled) |
| 100–1,000 GPUs | ~100K | 30 |
| 1,000–10,000 GPUs | ~1M | 60 |
| > 10,000 GPUs | ~10M+ | 60 + dimension pruning |

## References

- [Handle High-Cardinality Metrics in OTel Without Blowing Budget](https://oneuptime.com/blog/post/2026-02-06-handle-high-cardinality-metrics-opentelemetry/view)
- [OTel Interval Processor](https://oneuptime.com/blog/post/2026-02-06-interval-processor-opentelemetry-collector/view)
- [Last9 Guide: OTel and High Cardinality](https://last9.io/guides/high-cardinality/opentelemetry-and-modern-tooling-for-high-cardinality/)
