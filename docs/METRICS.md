# l9gpu Metrics Reference

This document is the source of truth for all metrics emitted by the l9gpu telemetry stack.
`l9gpu/exporters/metric_names.py` is the authoritative code-level mapping from Python field
names to OTel metric names.

## How to Read This Document

Each section covers one integration. Metrics are listed in tables with these columns:

| Column | Meaning |
|--------|---------|
| **OTel / Prometheus Name** | The metric name as written to the backend |
| **Unit** | [OTel UCUM](https://ucum.org/) convention: `1` = dimensionless fraction, `By` = bytes, `By/s` = bytes/sec, `Cel` = Celsius, `W` = watts, `MHz` = megahertz, `mJ` = millijoules, `{x}` = dimensioned count |
| **Disambiguating Attribute** | Extra data-point attribute(s) that distinguish rows sharing the same metric name |
| **Description** | One-line purpose |

**Resource attributes** (`k8s.cluster.name`, `host.name`) are set on the OTel Resource, not on
individual data points, for all NVML-based integrations.

---

## 1. NVML Device Metrics  (`l9gpu nvml_monitor`)

Source: NVML library via `l9gpu/monitoring/cli/nvml_monitor.py` and
`l9gpu/exporters/otel.py`.

**Data-point attributes on every NVML metric:**

| Attribute | Example | Notes |
|-----------|---------|-------|
| `gpu.index` | `"0"` | Zero-based string index |
| `gpu.uuid` | `"GPU-abc123..."` | NVML UUID |
| `gpu.model` | `"Tesla T4"` | Device name from NVML |
| `k8s.cluster.name` | `"prod-cluster"` | Injected by `_resource_labels` in `Otel.__init__` |
| `host.name` | `"ip-10-0-1-5"` | Node hostname |

### 1.1 Core Utilization & Memory

| OTel Name | Unit | Disambiguating Attribute | Description |
|-----------|------|--------------------------|-------------|
| `gpu.utilization` | `1` | `gpu.task.type=compute` | Fraction of time the compute engine is executing kernels |
| `gpu.memory.utilization` | `1` | `gpu.task.type=memory_controller` | Fraction of time the memory controller is reading or writing |
| `gpu.memory.used.percent` | `{percent}` | — | GPU VRAM used as a percentage of total capacity |
| `gpu.memory.used` | `By` | — | GPU VRAM currently allocated (bytes) |
| `gpu.memory.total` | `By` | — | Total GPU VRAM on the device (bytes) |
| `gpu.memory.free` | `By` | — | GPU VRAM not yet allocated (bytes) |

### 1.2 Power & Thermal

| OTel Name | Unit | Disambiguating Attribute | Description |
|-----------|------|--------------------------|-------------|
| `gpu.temperature` | `Cel` | `gpu.temperature.sensor=edge` | GPU die temperature at the edge sensor |
| `gpu.power.draw` | `W` | — | Instantaneous power consumption in watts |
| `gpu.power.utilization` | `1` | — | Power draw as a fraction of the enforced software power limit |
| `gpu.power.state` | `{state}` | — | GPU P-state: 0 = max compute, 8 = idle; lower = more active |
| `gpu.fan.speed` | `1` | — | Fan speed as a fraction of maximum RPM (0–1) |

### 1.3 Clock Frequencies

| OTel Name | Unit | Disambiguating Attribute | Description |
|-----------|------|--------------------------|-------------|
| `gpu.clock.frequency` | `MHz` | `gpu.clock.type=graphics` | Current graphics engine clock frequency |
| `gpu.clock.frequency` | `MHz` | `gpu.clock.type=memory` | Current memory controller clock frequency |

### 1.4 Encode / Decode Engines

| OTel Name | Unit | Disambiguating Attribute | Description |
|-----------|------|--------------------------|-------------|
| `gpu.encode.utilization` | `1` | `gpu.task.type=encoder` | Fraction of time the hardware video encoder is active |
| `gpu.decode.utilization` | `1` | `gpu.task.type=decoder` | Fraction of time the hardware video decoder is active |

### 1.5 PCIe

| OTel Name | Unit | Disambiguating Attribute | Description |
|-----------|------|--------------------------|-------------|
| `gpu.pcie.throughput` | `By/s` | `gpu.interconnect.type=pcie, gpu.interconnect.direction=receive` | PCIe host-to-device read bandwidth; NVML returns KB/s, converted to bytes/s |
| `gpu.pcie.throughput` | `By/s` | `gpu.interconnect.type=pcie, gpu.interconnect.direction=transmit` | PCIe device-to-host write bandwidth; NVML returns KB/s, converted to bytes/s |
| `gpu.pcie.replay.count` | `{event}` | — | Cumulative PCIe replay counter; non-zero indicates link integrity errors |

### 1.6 NVLink

| OTel Name | Unit | Disambiguating Attribute | Description |
|-----------|------|--------------------------|-------------|
| `gpu.interconnect.throughput` | `By/s` | `gpu.interconnect.type=nvlink, gpu.interconnect.direction=receive` | NVLink aggregate receive bandwidth; always 0 on T4/A10G (no NVLink hardware) |
| `gpu.interconnect.throughput` | `By/s` | `gpu.interconnect.type=nvlink, gpu.interconnect.direction=transmit` | NVLink aggregate transmit bandwidth; always 0 on T4/A10G (no NVLink hardware) |

### 1.7 ECC Errors

Two distinct OTel names: `gpu.row_remap.count` tracks retired DRAM pages (permanent hardware
retirements); `gpu.ecc.errors` tracks volatile in-session error counts.

| OTel Name | Unit | Disambiguating Attribute | Description |
|-----------|------|--------------------------|-------------|
| `gpu.row_remap.count` | `{row}` | `gpu.ecc.error_type=correctable` | Cumulative retired-page count from correctable (SBE) memory errors |
| `gpu.row_remap.count` | `{row}` | `gpu.ecc.error_type=uncorrectable` | Cumulative retired-page count from uncorrectable (DBE) memory errors |
| `gpu.ecc.errors` | `{error}` | `gpu.ecc.error_type=correctable, gpu.ecc.count_type=volatile` | Correctable ECC errors this driver session; resets on driver restart |
| `gpu.ecc.errors` | `{error}` | `gpu.ecc.error_type=uncorrectable, gpu.ecc.count_type=volatile` | Uncorrectable ECC errors this driver session; resets on driver restart |

### 1.8 Throttle Reasons

All throttle metrics share the OTel name `gpu.throttle.reason`. The raw bitmask row has no
disambiguating attribute; the four boolean rows each carry a `gpu.throttle.cause` attribute.

| OTel Name | Unit | Disambiguating Attribute | Description |
|-----------|------|--------------------------|-------------|
| `gpu.throttle.reason` | `{bool}` | — | Raw NVML bitmask of all active clock-throttle reasons |
| `gpu.throttle.reason` | `{bool}` | `gpu.throttle.cause=power_software` | 1 if throttled by software power cap; 0 otherwise |
| `gpu.throttle.reason` | `{bool}` | `gpu.throttle.cause=temp_hardware` | 1 if throttled by hardware thermal limit; 0 otherwise |
| `gpu.throttle.reason` | `{bool}` | `gpu.throttle.cause=temp_software` | 1 if throttled by software thermal slowdown; 0 otherwise |
| `gpu.throttle.reason` | `{bool}` | `gpu.throttle.cause=syncboost` | 1 if throttled due to sync-boost across GPUs; 0 otherwise |

### 1.9 Reliability

| OTel Name | Unit | Disambiguating Attribute | Description |
|-----------|------|--------------------------|-------------|
| `gpu.xid.errors` | `{error}` | — | Cumulative XID error count; non-zero means a GPU firmware or driver fault |
| `gpu.energy.consumption` | `mJ` | — | Cumulative energy consumed since driver load (millijoules) |

---

## 2. Host Aggregate Metrics  (`l9gpu nvml_monitor`, computed per node)

Source: `l9gpu/schemas/host_metrics.py`. Computed by `nvml_monitor` after each polling cycle
across all GPUs on the node.

**Data-point attributes:** `k8s.cluster.name`, `host.name`

| OTel Name | Unit | Description |
|-----------|------|-------------|
| `gpu.utilization.max` | `1` | Maximum GPU compute utilization across all GPUs on the node |
| `gpu.utilization.min` | `1` | Minimum GPU compute utilization across all GPUs on the node |
| `gpu.utilization.avg` | `1` | Average GPU compute utilization across all GPUs on the node |
| `host.memory.utilization` | `1` | Host system RAM utilization as a fraction (0–1) |

---

## 3. DCGM Metrics — OTel Re-export  (`l9gpu dcgm_monitor`)

Source: Scraped from dcgm-exporter Prometheus endpoint (default
`http://localhost:9400/metrics`) then re-exported as OTel metrics by `dcgm_monitor`.
Schema: `l9gpu/schemas/dcgm_metrics.py`.

**Data-point attributes on every DCGM OTel metric:**

| Attribute | Notes |
|-----------|-------|
| `gpu.index` | Zero-based string index |
| `gpu.uuid` | DCGM UUID |
| `gpu.model` | Device model name |
| `k8s.cluster.name` | Propagated from OTel resource attributes |

All values are fractions in [0.0, 1.0]. The DCGM profiling lock must be held; only one
profiling client may run concurrently (e.g. nvprof, Nsight, or dcgm-exporter).

| OTel Name | Unit | DCGM Field | Description |
|-----------|------|-----------|-------------|
| `gpu.sm.active` | `1` | `DCGM_FI_PROF_SM_ACTIVE` | Fraction of time at least one warp is active on any SM |
| `gpu.dram.active` | `1` | `DCGM_FI_PROF_DRAM_ACTIVE` | Fraction of time the DRAM interface is actively transferring data |
| `gpu.gr_engine.active` | `1` | `DCGM_FI_PROF_GR_ENGINE_ACTIVE` | Fraction of time the graphics/compute engine is active |
| `gpu.pipe.tensor.active` | `1` | `DCGM_FI_PROF_PIPE_TENSOR_ACTIVE` | Fraction of cycles tensor (matrix) cores are executing instructions |
| `gpu.pipe.fp64.active` | `1` | `DCGM_FI_PROF_PIPE_FP64_ACTIVE` | Fraction of cycles the FP64 double-precision pipe is active |
| `gpu.pipe.fp32.active` | `1` | `DCGM_FI_PROF_PIPE_FP32_ACTIVE` | Fraction of cycles the FP32 single-precision pipe is active |
| `gpu.pipe.fp16.active` | `1` | `DCGM_FI_PROF_PIPE_FP16_ACTIVE` | Fraction of cycles the FP16/BF16 half-precision pipe is active |

---

## 4. DCGM Metrics — Native Prometheus  (dcgm-exporter DaemonSet)

Source: dcgm-exporter Prometheus scrape → OTel Collector `prometheus` receiver → backend.
Metric list configured in `deploy/helm/l9gpu/examples/dcgm-metrics.csv`.

**Labels added by dcgm-exporter on every metric:**

| Label | Example | Notes |
|-------|---------|-------|
| `gpu` | `"0"` | Zero-based device index |
| `UUID` | `"GPU-abc123..."` | NVML UUID |
| `modelName` | `"Tesla T4"` | Device name |
| `Hostname` | `"ip-10-0-1-5"` | Node hostname |
| `k8s_cluster_name` | `"prod-cluster"` | Injected by OTel Collector resource processor |

### 4.1 Core Device Metrics

| Prometheus Metric | Type | Unit | Description |
|-------------------|------|------|-------------|
| `DCGM_FI_DEV_GPU_UTIL` | gauge | `%` | GPU compute utilization |
| `DCGM_FI_DEV_MEM_COPY_UTIL` | gauge | `%` | Memory controller utilization |
| `DCGM_FI_DEV_FB_FREE` | gauge | `MiB` | Framebuffer (VRAM) free |
| `DCGM_FI_DEV_FB_USED` | gauge | `MiB` | Framebuffer (VRAM) used |
| `DCGM_FI_DEV_FB_TOTAL` | gauge | `MiB` | Framebuffer (VRAM) total |
| `DCGM_FI_DEV_POWER_USAGE` | gauge | `W` | Instantaneous power draw |
| `DCGM_FI_DEV_GPU_TEMP` | gauge | `°C` | GPU die temperature |
| `DCGM_FI_DEV_MEMORY_TEMP` | gauge | `°C` | VRAM temperature |
| `DCGM_FI_DEV_SM_CLOCK` | gauge | `MHz` | Streaming multiprocessor (SM) clock frequency |
| `DCGM_FI_DEV_MEM_CLOCK` | gauge | `MHz` | Memory controller clock frequency |
| `DCGM_FI_DEV_ECC_SBE_VOL_TOTAL` | counter | `{error}` | Volatile single-bit (correctable) ECC errors; resets on driver restart |
| `DCGM_FI_DEV_ECC_DBE_VOL_TOTAL` | counter | `{error}` | Volatile double-bit (uncorrectable) ECC errors; resets on driver restart |
| `DCGM_FI_DEV_ECC_SBE_AGG_TOTAL` | counter | `{error}` | Aggregate single-bit ECC errors; lifetime cumulative |
| `DCGM_FI_DEV_ECC_DBE_AGG_TOTAL` | counter | `{error}` | Aggregate double-bit ECC errors; lifetime cumulative |
| `DCGM_FI_DEV_PCIE_TX_THROUGHPUT` | counter | `KB/s` | PCIe transmit throughput since last query |
| `DCGM_FI_DEV_PCIE_RX_THROUGHPUT` | counter | `KB/s` | PCIe receive throughput since last query |
| `DCGM_FI_DEV_PCIE_REPLAY_COUNTER` | counter | `{event}` | Cumulative PCIe replay counter; non-zero indicates link errors |
| `DCGM_FI_DEV_XID_ERRORS` | gauge | `{error}` | Most recent XID error code; non-zero means a GPU fault occurred |

### 4.2 Profiling Counters

Require the DCGM profiling lock. Only one profiling client may run concurrently (e.g. nvprof,
Nsight, dcgm-exporter). Values are fractions [0.0–1.0]; multiply by 100 for percentages in
dashboards.

| Prometheus Metric | Type | Hardware Notes | Description |
|-------------------|------|----------------|-------------|
| `DCGM_FI_PROF_GR_ENGINE_ACTIVE` | gauge | All DCGM-supported GPUs | Fraction of time the graphics/compute engine is active |
| `DCGM_FI_PROF_SM_ACTIVE` | gauge | All DCGM-supported GPUs | Fraction of time at least one warp is active on an SM |
| `DCGM_FI_PROF_SM_OCCUPANCY` | gauge | All DCGM-supported GPUs | Fraction of warps resident on SM vs. theoretical maximum |
| `DCGM_FI_PROF_PIPE_TENSOR_ACTIVE` | gauge | Volta+ (T4, V100, A10G, A100, H100) | Fraction of cycles tensor cores are executing instructions |
| `DCGM_FI_PROF_PIPE_FP64_ACTIVE` | gauge | V100, A100, H100; always 0 on T4/A10G | Fraction of cycles the FP64 double-precision pipe is active |
| `DCGM_FI_PROF_PIPE_FP32_ACTIVE` | gauge | All DCGM-supported GPUs | Fraction of cycles the FP32 single-precision pipe is active |
| `DCGM_FI_PROF_PIPE_FP16_ACTIVE` | gauge | Volta+ | Fraction of cycles the FP16/BF16 half-precision pipe is active |
| `DCGM_FI_PROF_DRAM_ACTIVE` | gauge | All DCGM-supported GPUs | Fraction of cycles DRAM is actively transferring data |
| `DCGM_FI_PROF_PCIE_TX_BYTES` | counter | All DCGM-supported GPUs | PCIe transmit bandwidth (bytes/sec) |
| `DCGM_FI_PROF_PCIE_RX_BYTES` | counter | All DCGM-supported GPUs | PCIe receive bandwidth (bytes/sec) |
| `DCGM_FI_PROF_NVLINK_TX_BYTES` | counter | A100/H100 SXM only; always 0 on T4/A10G | NVLink transmit bandwidth (bytes/sec) |
| `DCGM_FI_PROF_NVLINK_RX_BYTES` | counter | A100/H100 SXM only; always 0 on T4/A10G | NVLink receive bandwidth (bytes/sec) |

---

## 5. vLLM Metrics  (`l9gpu vllm_monitor`)

Source: Scraped from the vLLM Prometheus endpoint (default `http://localhost:8000/metrics`),
re-exported as OTel metrics. Schema: `l9gpu/schemas/vllm_metrics.py`.

**Version note:** In vLLM ≥ 0.6, `gpu_cache_usage_perc` and `cpu_cache_usage_perc` were
unified into `kv_cache_usage_perc`. `vllm_monitor` handles both via fallback parsing
(`vllm_monitor.py:77-78`).

**Data-point attributes:** `k8s.cluster.name`, `host.name`

| OTel Name | Unit | Disambiguating Attribute | Description |
|-----------|------|--------------------------|-------------|
| `vllm.prompt.throughput` | `{token}/s` | — | Rate of prompt tokens processed per second (derived from counter delta) |
| `vllm.generation.throughput` | `{token}/s` | — | Rate of generated tokens per second (derived from counter delta) |
| `vllm.request.latency` | `s` | `quantile=p50` | Median end-to-end request latency (estimated from histogram buckets) |
| `vllm.request.latency` | `s` | `quantile=p95` | 95th-percentile end-to-end request latency |
| `vllm.request.latency` | `s` | `quantile=p99` | 99th-percentile end-to-end request latency |
| `vllm.ttft` | `s` | `quantile=p50` | Median time-to-first-token (from request receipt to first output token) |
| `vllm.ttft` | `s` | `quantile=p95` | 95th-percentile time-to-first-token |
| `vllm.cache.usage` | `1` | `cache.type=gpu` | GPU KV-cache utilization as a fraction (0–1) |
| `vllm.cache.usage` | `1` | `cache.type=cpu` | CPU KV-cache (swap) utilization as a fraction (0–1) |
| `vllm.requests.running` | `{request}` | — | Number of requests currently being decoded by the engine |
| `vllm.requests.waiting` | `{request}` | — | Number of requests in the prefill queue waiting for a free slot |
| `vllm.requests.swapped` | `{request}` | — | Number of requests whose KV cache has been swapped to CPU |

---

## 6. NIM Metrics  (`l9gpu nim_monitor`)

Source: Scraped from the NVIDIA NIM Prometheus endpoint (default
`http://localhost:8000/metrics`). Schema: `l9gpu/schemas/nim_metrics.py`.

> **Note:** NIM monitoring is not deployed in the current cluster. These metrics become
> available when `nim_monitor` is configured against a running NIM container.

**Data-point attributes:** `k8s.cluster.name`, `host.name`

| OTel Name | Unit | Disambiguating Attribute | Description |
|-----------|------|--------------------------|-------------|
| `nim.requests.total` | `{request}` | — | Cumulative total inference requests received |
| `nim.requests.failed` | `{request}` | — | Cumulative total inference requests that failed |
| `nim.request.latency` | `s` | `quantile=p50` | Median end-to-end request latency (estimated from histogram buckets) |
| `nim.request.latency` | `s` | `quantile=p99` | 99th-percentile end-to-end request latency |
| `nim.batch.size` | `{request}` | — | Rolling average batch size for inference executions |
| `nim.queue.depth` | `{request}` | — | Current number of requests waiting in the inference queue |
| `nim.kv_cache.usage` | `1` | — | GPU KV-cache utilization as a fraction (0–1) |

---

## 7. AMD Device Metrics  (`l9gpu amd_monitor`)

Source: AMD ROCm APIs via `l9gpu/schemas/amd_device_metrics.py`.

`AMDDeviceMetrics` extends `DeviceMetrics` — all §1 NVML baseline metrics apply where ROCm
provides equivalent data. The four fields below are AMD-specific additions.

> **Note:** Requires AMD GPU hardware (MI300X, MI325X, etc.).

| OTel Name | Unit | Disambiguating Attribute | Description |
|-----------|------|--------------------------|-------------|
| `gpu.interconnect.throughput` | `By/s` | `gpu.interconnect.type=xgmi` | Per-link XGMI (Infinity Fabric) bandwidth; 8 links on MI300X/MI325X |
| `gpu.ecc.errors` | `{error}` | _(per-block key varies)_ | Per-memory-block ECC correctable error counts; MI300X exposes 40+ blocks (`gpu.ecc.memory_block`) |
| `gpu.temperature` | `Cel` | `gpu.temperature.sensor=hotspot` | Junction/hotspot temperature — highest die reading, more representative than edge sensor |
| `gpu.temperature` | `Cel` | `gpu.temperature.sensor=memory` | HBM memory stack temperature |

---

## 8. Intel Gaudi Device Metrics  (`l9gpu gaudi_monitor`)

Source: Intel Gaudi HL-SMI via `l9gpu/schemas/gaudi_device_metrics.py`.

`GaudiDeviceMetrics` extends `DeviceMetrics` — all §1 NVML baseline metrics apply where
Gaudi HL-SMI provides equivalent data. The four fields below are Gaudi-specific additions.

> **Note:** Requires Intel Gaudi hardware (Gaudi 2, Gaudi 3). Gaudi 3 supports up to
> 24 × 200 GbE network ports.

| OTel Name | Unit | Disambiguating Attribute | Description |
|-----------|------|--------------------------|-------------|
| `gpu.interconnect.throughput` | `By/s` | `gpu.interconnect.direction=receive` | Aggregate network RX bandwidth across all Gaudi high-speed network ports |
| `gpu.interconnect.throughput` | `By/s` | `gpu.interconnect.direction=transmit` | Aggregate network TX bandwidth across all Gaudi high-speed network ports |
| `gpu.row_remap.count` | `{row}` | `gpu.row_remap.state=replaced` | Number of DRAM rows replaced due to errors |
| `gpu.row_remap.pending` | `{row}` | `gpu.row_remap.state=pending` | Number of DRAM rows flagged for replacement on next reboot |

---

## Appendix A — Common Labels

### A.1 NVML / OTel Data-Point Attributes

Set on individual data points (not the OTel Resource) by `l9gpu/exporters/otel.py` via
`FIELD_DATA_POINT_ATTRIBUTES` in `metric_names.py`:

| Attribute | Values | Used by |
|-----------|--------|---------|
| `gpu.index` | `"0"`, `"1"`, … | All NVML, DCGM OTel, AMD, Gaudi |
| `gpu.uuid` | `"GPU-abc123..."` | All NVML, DCGM OTel, AMD, Gaudi |
| `gpu.model` | `"Tesla T4"` | All NVML, DCGM OTel, AMD, Gaudi |
| `gpu.task.type` | `compute`, `memory_controller`, `encoder`, `decoder` | `gpu.utilization`, `gpu.memory.utilization`, encode/decode |
| `gpu.temperature.sensor` | `edge`, `hotspot`, `memory` | `gpu.temperature` |
| `gpu.clock.type` | `graphics`, `memory` | `gpu.clock.frequency` |
| `gpu.interconnect.type` | `nvlink`, `pcie`, `xgmi` | `gpu.interconnect.throughput`, `gpu.pcie.throughput` |
| `gpu.interconnect.direction` | `receive`, `transmit` | `gpu.interconnect.throughput`, `gpu.pcie.throughput` |
| `gpu.ecc.error_type` | `correctable`, `uncorrectable` | `gpu.row_remap.count`, `gpu.ecc.errors` |
| `gpu.ecc.count_type` | `volatile` | `gpu.ecc.errors` (volatile rows only; absent on retired-page rows) |
| `gpu.throttle.cause` | `power_software`, `temp_hardware`, `temp_software`, `syncboost` | `gpu.throttle.reason` (boolean rows only) |
| `gpu.row_remap.state` | `replaced`, `pending` | `gpu.row_remap.count` (Gaudi), `gpu.row_remap.pending` |
| `quantile` | `p50`, `p95`, `p99` | `vllm.request.latency`, `vllm.ttft`, `nim.request.latency` |
| `cache.type` | `gpu`, `cpu` | `vllm.cache.usage` |

### A.2 DCGM Native Prometheus Labels

Added by dcgm-exporter to every scraped metric:

| Label | Description |
|-------|-------------|
| `gpu` | Zero-based device index (integer string) |
| `UUID` | NVML UUID |
| `modelName` | Device model name |
| `Hostname` | Pod or node hostname |
| `k8s_cluster_name` | Injected by the OTel Collector resource processor |

### A.3 OTel Resource Attributes

Set on the OTel Resource (not individual data points) by the NVML exporter:

| Attribute | Description |
|-----------|-------------|
| `k8s.cluster.name` | Kubernetes cluster name (passed via `--cluster` flag or env) |
| `host.name` | Node hostname |
| `cloud.availability_zone` | Cloud AZ injected by k8shelper from node labels (if present) |
| `cloud.region` | Cloud region injected by k8shelper from node labels (if present) |
| `service.name` | Identifies the collector service |

---

## Appendix B — Deployment Mapping

| Integration | How Deployed | Metrics Sections |
|-------------|-------------|-----------------|
| NVML | `l9gpu-monitoring` DaemonSet running `nvml_monitor --sink otel` | §1 Device, §2 Host |
| DCGM OTel re-export | `dcgm_monitor --dcgm-endpoint http://localhost:9400/metrics` in the same DaemonSet | §3 |
| DCGM Native | `dcgm-exporter` DaemonSet → OTel Collector `prometheus` receiver → backend | §4 |
| vLLM | `vllm-monitor` Deployment running `l9gpu vllm_monitor --sink otel` | §5 |
| NIM | `nim_monitor` (not deployed in current cluster; point at NIM container endpoint) | §6 |
| AMD | `amd_monitor` (requires AMD GPU hardware: MI300X, MI325X) | §7 |
| Gaudi | `gaudi_monitor` (requires Intel Gaudi hardware: Gaudi 2/3) | §8 |

---

## §9 — Phases 6-17 New Metrics (March 2026)

### Phase 6: Advanced DCGM Profiling + MIG

| OTel Name | Field | Unit | Notes |
|---|---|---|---|
| `gpu.sm.occupancy` | `sm_occupancy` | `1` | Warp residency on SM |
| `gpu.interconnect.throughput` | `nvlink_tx_bytes` / `nvlink_rx_bytes` | `By/s` | DCGM profiling gauge |
| `gpu.pcie.throughput` | `prof_pcie_tx_bytes` / `prof_pcie_rx_bytes` | `By/s` | Supersedes deprecated DEV_PCIE |

**MIG attributes:** `gpu.mig.enabled`, `gpu.mig.instance_id` — set when MIG detected in dcgm-exporter labels.

### Phase 7: Triton Inference Server

| OTel Name | Field | Unit |
|---|---|---|
| `triton.requests.success` | `triton_requests_success_per_sec` | `{request}/s` |
| `triton.requests.failed` | `triton_requests_failed_per_sec` | `{request}/s` |
| `triton.request.latency` | `triton_avg_request_latency_us` | `us` |
| `triton.queue.latency` | `triton_avg_queue_latency_us` | `us` |
| `triton.compute.latency` | `triton_avg_compute_infer_latency_us` | `us` |
| `triton.queue.depth` | `triton_queue_depth` | `{request}` |
| `triton.batch.size` | `triton_avg_batch_size` | `{request}` |

Per-model: `model.name` and `model.version` data-point attributes.

### Phase 8: Extended vLLM/NIM

| OTel Name | Field | Unit | Notes |
|---|---|---|---|
| `vllm.itl` | `itl_p50/p95/p99` | `s` | Inter-token latency (v0.7+) |
| `vllm.prefill.duration` | `prefill_duration_p50/p95` | `s` | Disaggregated (v0.8+) |
| `vllm.decode.duration` | `decode_duration_p50/p95` | `s` | Disaggregated (v0.8+) |
| `vllm.cache.hit_rate` | `cache_hit_rate` | `1` | Counter-delta (v0.8+) or deprecated gauge |
| `vllm.cache.evictions` | `cache_evictions_per_sec` | `{block}/s` | KV cache pressure |
| `vllm.spec_decode.acceptance_rate` | `spec_decode_acceptance_rate` | `1` | From counter deltas |
| `vllm.spec_decode.efficiency` | `spec_decode_efficiency` | `1` | Mean acceptance length |
| `vllm.scheduler.preemptions` | `preemptions_per_sec` | `{event}/s` | Continuous batching pressure |
| `vllm.requests.finished` | by `finish_reason` (stop/length/abort) | `{request}/s` | |
| `nim.itl` | `nim_itl_p50/p95` | `s` | NIM inter-token latency |

### Phase 9: SGLang + TGI

**SGLang** (`sglang.*`): throughput, TTFT, ITL, E2E latency, cache hit rate, queue depths.
**TGI** (`tgi.*`): request/queue/inference latency, TPOT, batch size, token distributions.

### Phase 10: GPU Fleet Health

| OTel Name | Field | Unit | Notes |
|---|---|---|---|
| `gpu.xid.error_rate` | `xid_error_rate` | `{error}/h` | Sliding window |
| `gpu.ecc.sbe_rate` | `ecc_sbe_rate` | `{error}/h` | Upward trend = failure |
| `gpu.pcie.link.downtraining` | `pcie_link_downtraining` | `{bool}` | 1 = degraded |
| `gpu.thermal.ramp_rate` | `thermal_ramp_rate` | `Cel/min` | >2.0 = cooling failure |
| `gpu.health.score` | `health_score` | `1` | Composite 0-100 |

### Phase 11: Cost + Carbon

| OTel Name | Field | Unit |
|---|---|---|
| `gpu.cost.per_gpu_hour` | `cost_per_gpu_hour` | `USD/h` |
| `gpu.cost.per_prompt_token` | `cost_per_prompt_token` | `USD/{token}` |
| `gpu.cost.per_generation_token` | `cost_per_generation_token` | `USD/{token}` |
| `gpu.efficiency.tokens_per_watt` | `tokens_per_watt` | `{token}/W` |
| `gpu.energy.co2_rate` | `co2_rate_grams_per_sec` | `g/s` |

### Phase 12: GenAI OTel Conventions

Opt-in via `--emit-genai-namespace`. Maps all inference metrics to `gen_ai.*`:
`gen_ai.client.token.usage`, `gen_ai.server.request.duration`,
`gen_ai.server.time_to_first_token`, `gen_ai.server.time_per_output_token`,
`gen_ai.server.cache.utilization`, `gen_ai.server.cache.hit_rate`.

Resource attribute: `gen_ai.provider.name` (+ deprecated `gen_ai.system` alias).

### Phase 13: NCCL Collective Communication

| OTel Name | Field | Unit |
|---|---|---|
| `nccl.collective.bandwidth` | `bandwidth_bytes_per_sec` | `By/s` |
| `nccl.collective.bus_bandwidth` | `bus_bandwidth_bytes_per_sec` | `By/s` |
| `nccl.collective.duration` | `duration_us` | `us` |
| `nccl.rank.straggler` | `is_straggler` | `{bool}` |

Attributes: `nccl.collective.type`, `nccl.rank`.

### Phase 15: Distributed Training

| OTel Name | Field | Unit |
|---|---|---|
| `training.mfu` | `mfu` | `1` |
| `training.tflops` | `tflops` | `TFLOPS` |
| `training.gradient.norm` | `gradient_norm` | `1` |
| `training.checkpoint.save_duration` | `checkpoint_save_duration` | `s` |
| `training.dataloader.wait` | `dataloader_wait` | `s` |

### Phase 16-17: Platform

- OTel Collector config with full L3-L6 pipeline (hostmetrics, kubeletstats, k8s_cluster)
- Grace-Hopper / Blackwell unified memory: `gpu.memory.unified.used`, `gpu.memory.unified.total`

---

## §10 — Metrics by Observability Layer (L1–L8)

This section cross-references all l9gpu metrics against the 8-layer GPU observability architecture.

### L1 — GPU Hardware / Silicon

**Sources:** NVML, DCGM Exporter (:9400), amdsmi, hl-smi
**CLI:** `nvml_monitor`, `amd_monitor`, `gaudi_monitor`, `dcgm_monitor`, `fleet_health_monitor`

| Category | OTel Name | Unit | l9gpu CLI |
|----------|-----------|------|-----------|
| **Compute** | `gpu.utilization` | `1` | nvml/amd/gaudi |
| | `gpu.sm.active` | `1` | dcgm |
| | `gpu.sm.occupancy` | `1` | dcgm |
| | `gpu.pipe.tensor.active` | `1` | dcgm |
| | `gpu.pipe.fp16.active` | `1` | dcgm |
| | `gpu.pipe.fp32.active` | `1` | dcgm |
| | `gpu.pipe.fp64.active` | `1` | dcgm |
| | `gpu.gr_engine.active` | `1` | dcgm (MIG fallback) |
| | `gpu.dram.active` | `1` | dcgm |
| | `gpu.encode.utilization` | `1` | nvml |
| | `gpu.decode.utilization` | `1` | nvml |
| **Memory** | `gpu.memory.used` | `By` | nvml/amd/gaudi |
| | `gpu.memory.total` | `By` | nvml/amd/gaudi |
| | `gpu.memory.free` | `By` | nvml/amd/gaudi |
| | `gpu.memory.utilization` | `1` | nvml/amd/gaudi |
| | `gpu.memory.used.percent` | `{percent}` | nvml/amd/gaudi |
| | `gpu.memory.unified.used` | `By` | nvml (GH200/GB200) |
| | `gpu.memory.unified.total` | `By` | nvml (GH200/GB200) |
| **Interconnect** | `gpu.interconnect.throughput` (nvlink) | `By/s` | nvml, dcgm |
| | `gpu.interconnect.throughput` (xgmi) | `By/s` | amd |
| | `gpu.interconnect.throughput` (gaudi net) | `By/s` | gaudi |
| | `gpu.pcie.throughput` | `By/s` | nvml, dcgm |
| **Power/Thermal** | `gpu.power.draw` | `W` | nvml/amd/gaudi |
| | `gpu.power.utilization` | `1` | nvml |
| | `gpu.temperature` (edge/hotspot/memory) | `Cel` | nvml/amd/gaudi |
| | `gpu.clock.frequency` (graphics/memory) | `MHz` | nvml/amd |
| | `gpu.throttle.reason` | `{bool}` | nvml |
| | `gpu.fan.speed` | `1` | nvml |
| | `gpu.energy.consumption` | `mJ` | nvml |
| **Reliability** | `gpu.ecc.errors` | `{error}` | nvml/amd |
| | `gpu.ecc.sbe_rate` | `{error}/h` | fleet_health |
| | `gpu.ecc.dbe_total` | `{error}` | fleet_health |
| | `gpu.row_remap.count` | `{row}` | nvml/amd/gaudi |
| | `gpu.row_remap.available` | `{row}` | fleet_health |
| | `gpu.xid.errors` | `{error}` | nvml |
| | `gpu.xid.error_rate` | `{error}/h` | fleet_health |
| | `gpu.pcie.link.downtraining` | `{bool}` | fleet_health |
| | `gpu.thermal.ramp_rate` | `Cel/min` | fleet_health |
| | `gpu.health.score` | `1` | fleet_health |

### L2 — CUDA Runtime & Profiling

**Sources:** CUPTI (xpu-perf), NCCL Inspector
**CLI:** `nccl_monitor` (Phase 13); xpu-perf DaemonSet (Phase 14 — not yet implemented)

| Category | OTel Name | Unit | l9gpu CLI |
|----------|-----------|------|-----------|
| **NCCL Collectives** | `nccl.collective.bandwidth` | `By/s` | nccl_monitor |
| | `nccl.collective.bus_bandwidth` | `By/s` | nccl_monitor |
| | `nccl.collective.duration` | `us` | nccl_monitor |
| | `nccl.collective.message_size` | `By` | nccl_monitor |
| | `nccl.rank.straggler` | `{bool}` | nccl_monitor |
| **CUDA Kernels** | `xpu.kernel.calls` | counter | xpu-perf (TBD) |
| | `xpu.kernel.duration.avg` | `ns` | xpu-perf (TBD) |
| | `cuda.kernel.execution` (trace span) | — | xpu-perf (TBD) |

### L3 — Host / OS / System

**Sources:** OTel Collector `hostmetrics` receiver (shipped via otel-collector-config.yaml)
**Not collected by l9gpu Python directly** — delegated to standard OTel Collector

| Category | OTel Name | Source |
|----------|-----------|-------|
| CPU | `system.cpu.utilization` | hostmetrics |
| Memory | `system.memory.utilization` | hostmetrics |
| Disk | `system.disk.io` | hostmetrics |
| Network | `system.network.io` | hostmetrics |
| Process | `process.cpu.utilization`, `process.memory.usage` | hostmetrics |
| Host GPU agg | `gpu.utilization.max/min/avg`, `host.memory.utilization` | nvml_monitor |

### L4 — Container & Orchestration

**Sources:** OTel Collector `kubeletstats` + `k8s_cluster` receivers; l9gpu `k8sprocessor` (Go)

| Category | OTel Name | Source |
|----------|-----------|-------|
| Container | `container.cpu.usage`, `container.memory.working_set` | kubeletstats |
| Pod metadata | `k8s.pod.name`, `k8s.namespace.name`, `k8s.node.name` | k8sprocessor |
| Workload owners | `k8s.deployment.name`, `k8s.job.name`, `k8s.statefulset.name` | k8sprocessor |
| Cloud topology | `cloud.availability_zone`, `cloud.region` | k8sprocessor |
| Slurm jobs | `slurm.job.id`, `slurm.job.user`, `slurm.job.name` | slurm_job_monitor |

### L5 — ML Framework / Runtime

**Sources:** `l9gpu.training` Python library (PyTorch hooks)
**CLI:** N/A (library import, not a CLI monitor)

| Category | OTel Name | Unit |
|----------|-----------|------|
| Efficiency | `training.mfu` | `1` |
| | `training.tflops` | `TFLOPS` |
| | `training.step_time` | `s` |
| Gradients | `training.gradient.norm` | `1` |
| | `training.gradient.nan_count` | `{param}` |
| | `training.gradient.clip_rate` | `1` |
| Loss | `training.loss` | `1` |
| DataLoader | `training.dataloader.wait` | `s` |
| Checkpoint | `training.checkpoint.save_duration` | `s` |
| | `training.checkpoint.save_bandwidth` | `By/s` |

### L6 — Inference Engine / Serving Layer

**Sources:** vLLM, NIM, Triton, SGLang, TGI Prometheus endpoints
**CLI:** `vllm_monitor`, `nim_monitor`, `triton_monitor`, `sglang_monitor`, `tgi_monitor`

| Category | OTel Name | Engines |
|----------|-----------|---------|
| **Latency** | `*.request.latency` (p50/p95/p99) | vLLM, NIM, Triton, SGLang, TGI |
| | `*.ttft` / `gen_ai.server.time_to_first_token` | vLLM, SGLang |
| | `*.itl` / `gen_ai.server.time_per_output_token` | vLLM, NIM, SGLang, TGI |
| | `*.prefill.duration` | vLLM |
| | `*.decode.duration` | vLLM |
| | `*.queue.latency` | Triton, TGI |
| | `*.compute.latency` | Triton |
| **Throughput** | `*.prompt.throughput` | vLLM, SGLang |
| | `*.generation.throughput` | vLLM, SGLang |
| | `*.requests.success` | vLLM, Triton |
| **KV Cache** | `*.cache.usage` | vLLM, NIM |
| | `*.cache.hit_rate` | vLLM, SGLang |
| | `*.cache.evictions` | vLLM |
| **Queue** | `*.requests.running/waiting/swapped` | vLLM, SGLang |
| | `*.queue.depth` | Triton, NIM |
| **Batching** | `*.batch.size` | Triton, TGI |
| | `*.scheduler.preemptions` | vLLM |
| **Spec Decode** | `*.spec_decode.acceptance_rate` | vLLM |
| | `*.spec_decode.efficiency` | vLLM |

### L7 — API Gateway / Application

**Sources:** GenAI OTel conventions (opt-in via `--emit-genai-namespace`)

| Category | OTel Name | Notes |
|----------|-----------|-------|
| Token usage | `gen_ai.client.token.usage` | `gen_ai.token.type=input/output` |
| Duration | `gen_ai.server.request.duration` | p50/p95/p99 |
| TTFT | `gen_ai.server.time_to_first_token` | p50/p95 |
| ITL | `gen_ai.server.time_per_output_token` | p50/p95 |
| Cache | `gen_ai.server.cache.utilization` | gpu/cpu |
| | `gen_ai.server.cache.hit_rate` | |
| Provider | `gen_ai.provider.name` | resource attribute |

HTTP/routing/rate-limiting: delegated to customer's OTel SDK instrumentation.

### L8 — Business / SLO / Cost

**Sources:** `cost_monitor` (GPU cost + carbon), fleet_health `health_score`
**CLI:** `cost_monitor`

| Category | OTel Name | Unit |
|----------|-----------|------|
| **Cost** | `gpu.cost.per_gpu_hour` | `USD/h` |
| | `gpu.cost.rate` | `USD/s` |
| | `gpu.cost.per_prompt_token` | `USD/{token}` |
| | `gpu.cost.per_generation_token` | `USD/{token}` |
| | `gpu.cost.idle_rate` | `USD/s` |
| **Efficiency** | `gpu.efficiency.tokens_per_watt` | `{token}/W` |
| | `gpu.efficiency.joules_per_token` | `J/{token}` |
| | `gpu.idle` | `{bool}` |
| **Carbon** | `gpu.energy.co2_intensity` | `g/kWh` |
| | `gpu.energy.co2_rate` | `g/s` |
| **Health** | `gpu.health.score` | `1` (0-100) |

SLO alerting: implement via recording rules in backend (Prometheus/Grafana/Last9).
Pre-built alert rules are available in `alerts/prometheus/` (PrometheusRule CRDs) and
`alerts/grafana/` (Grafana Unified Alerting JSON). Deploy via Helm with `alerts.enabled=true`.

### Recommended Alert Thresholds

| Metric | Warning | Critical |
|--------|---------|----------|
| `gpu.temperature` | > 80°C | > 90°C |
| `gpu.memory.used / total` | > 85% | > 95% |
| `gpu.ecc.dbe_total` | > 0 | > 0 |
| `gpu.throttle.reason` | any bit set | sustained > 5min |
| `*.cache.usage` (KV cache) | > 80% | > 92% |
| `*.ttft` (P99) | > 1s | > 3s |
| `*.itl` (P99) | > 100ms | > 250ms |
| `*.scheduler.preemptions` | > 0/min | > 10/min |
| `gpu.health.score` | < 80 | < 50 |
| `gpu.pcie.link.downtraining` | = 1 | sustained > 1min |
| `gpu.cost.idle_rate` | > 10% hours | > 25% hours |
