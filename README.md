<!-- Copyright (c) Meta Platforms, Inc. and affiliates. -->
# l9gpu

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Go](https://img.shields.io/badge/go-1.25%2B-00ADD8)
[![PyPI](https://img.shields.io/pypi/v/l9gpu)](https://pypi.org/project/l9gpu/)
[![Artifact Hub](https://img.shields.io/endpoint?url=https://artifacthub.io/badge/repository/l9gpu)](https://artifacthub.io/packages/search?repo=l9gpu)

DCGM exporter tells you a GPU is hot. It won't tell you whose job is frying it.

Most GPU observability stops at the hardware — utilization, temperature, ECC —
and hands you a `gpu.uuid` with no answer to the only question that matters:
*who's paying for this idle H100?*

`l9gpu` closes the loop. One agent per node emits vendor-neutral OTLP with
**workload attribution baked in** — Kubernetes pod, namespace, deployment;
Slurm job, user, partition. You point it at any OTLP backend and get
per-team, per-job, per-model accounting without building a pipeline.

It works on NVIDIA, AMD, and Intel Gaudi today. It will keep working on
whatever comes next because it emits OpenTelemetry, not a bespoke format.
There's no vendor backend in the agent itself. That's deliberate.

---

## Quick Start — Kubernetes

```bash
# Classic Helm repo
helm repo add l9gpu https://last9.github.io/gpu-telemetry
helm install l9gpu l9gpu/l9gpu -n monitoring --create-namespace \
  --set monitoring.sink=otel \
  --set monitoring.cluster=my-cluster \
  --set otlpSecretName=l9gpu-otlp

# or OCI
helm install l9gpu oci://ghcr.io/last9/charts/l9gpu --version 0.1.0 -n monitoring
```

Create the OTLP secret first:

```bash
kubectl create secret generic l9gpu-otlp -n monitoring \
  --from-literal=OTEL_EXPORTER_OTLP_ENDPOINT=<your-otlp-endpoint> \
  --from-literal=OTEL_EXPORTER_OTLP_HEADERS="Authorization=Bearer <your-token>"
```

AMD / Gaudi nodes: `--set collectors.nvidia=false --set collectors.amd=true`
(or `collectors.gaudi=true`).

Full Helm guide: [`docs/HELM.md`](./docs/HELM.md). Topology examples
(EKS + DCGM, multi-GPU, sidecar collector): [`deploy/helm/l9gpu/examples/`](./deploy/helm/l9gpu/examples).

## Quick Start — Bare Metal / systemd

```bash
pip install l9gpu
export OTEL_EXPORTER_OTLP_ENDPOINT=<your-otlp-endpoint>
export OTEL_EXPORTER_OTLP_HEADERS="Authorization=Bearer <your-token>"

l9gpu nvml_monitor  --sink otel --cluster my-cluster  # NVIDIA
l9gpu amd_monitor   --sink otel --cluster my-cluster  # AMD
l9gpu gaudi_monitor --sink otel --cluster my-cluster  # Intel Gaudi
```

Sanity-check without OTLP: `l9gpu nvml_monitor --sink stdout --once`.

systemd unit files: [`systemd/`](./systemd/).

---

## What l9gpu is not

- **Not a Prometheus exporter.** It emits OTLP. Your Collector handles
  Prometheus scraping if you want it.
- **Not a backend.** `l9gpu` exports standard OTLP to whatever speaks OTLP.
  There's no Last9 lock-in in the agent.
- **Not a DCGM replacement.** DCGM profiling (SM occupancy, tensor pipe,
  NVLink) is complementary — bundle both through one Collector pipeline.
- **Not only NVIDIA.** AMD MI300X / MI325X and Intel Gaudi 2/3 are first-class.

---

## Architecture

<p align="center">
  <img src="https://raw.githubusercontent.com/last9/gpu-telemetry/main/docs/diagrams/l9gpu_architecture_flow.svg" alt="l9gpu architecture flow" width="780"/>
</p>

Collectors on each node normalize NVML / DCGM / amdsmi / hl-smi into the
`gpu.*` OTel namespace and ship OTLP to a Collector. The Collector enriches
with [`k8sprocessor`](./k8sprocessor/) or [`slurmprocessor`](./slurmprocessor/)
and fans out.

Every cycle (default 60s) emits **metrics** (one OTLP gauge per GPU per
metric) and **logs** (one OTLP log per GPU per cycle with the full snapshot —
useful for backends that prefer log-shaped events or for replaying history).

Full walk-through: [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md).

---

## Workload attribution

**Kubernetes** — [`k8sprocessor`](./k8sprocessor/) enriches each GPU data
point with `k8s.pod.name`, `k8s.namespace.name`, `k8s.deployment.name`,
`k8s.job.name`, `cloud.availability_zone`, `cloud.region`. Setup,
RBAC, label allow-lists: [`docs/K8S_WORKLOAD_ATTRIBUTION.md`](./docs/K8S_WORKLOAD_ATTRIBUTION.md).

**Slurm** — [`slurmprocessor`](./slurmprocessor/) attaches `slurm.job.id`,
`slurm.user`, `slurm.account`, partition, QoS:

```yaml
processors:
  slurm:
    cache_duration: 60
    cache_filepath: /tmp/slurmprocessor_cache.json
    query_slurmctld: false
```

Full config: [`slurmprocessor/README.md`](./slurmprocessor/README.md).

---

## Dashboards & alerts

Pre-built Grafana dashboards in [`dashboards/grafana/`](./dashboards/grafana/) —
multi-cluster fleet, per-pod workload, health/reliability (ECC, throttling,
XID), DCGM profiling, inference engines (vLLM, SGLang, TGI, Triton, NIM),
fleet efficiency / idle detection.

Alert rules in [`alerts/prometheus/`](./alerts/prometheus/) (17 `PrometheusRule`
CRDs) and [`alerts/grafana/`](./alerts/grafana/). Enable via Helm:
`helm upgrade --set alerts.enabled=true …`.

---

## Pre-built collector

Skip `ocb` and run a ready-made Collector with `k8sprocessor` +
`slurmprocessor` baked in:

```bash
docker run --rm -v $PWD/config.yaml:/etc/l9gpu/config.yaml:ro \
  ghcr.io/last9/l9gpu-collector:latest --config=/etc/l9gpu/config.yaml
```

Details and binary/tarball install: [`docs/COLLECTOR.md`](./docs/COLLECTOR.md).

---

## Components

| Directory | Language | Role |
|---|---|---|
| [`l9gpu/`](./l9gpu/) | Python | Node-level collector (DaemonSet / systemd). Emits OTLP metrics + logs. |
| [`k8sprocessor/`](./k8sprocessor/) | Go | OTel Collector processor. Enriches with K8s pod / workload / cloud metadata. |
| [`slurmprocessor/`](./slurmprocessor/) | Go | OTel Collector processor. Enriches with Slurm job metadata. |
| [`k8shelper/`](./k8shelper/) | Go | Shared K8s API helper library. |
| [`shelper/`](./shelper/) | Go | Shared Slurm helper library. |

---

## Hardware support

NVIDIA A100, H100 / H200, B200 / GB200, T4, A10, L4 (NVML + DCGM)  ·  AMD
MI300X, MI325X (amdsmi)  ·  Intel Gaudi 2, Gaudi 3 (hl-smi).

Full metric catalog with units and attributes: [`docs/METRICS.md`](./docs/METRICS.md).

---

## Demo

One-command EKS stack — vLLM + SGLang + TGI + Triton alongside l9gpu NVML,
DCGM, cost, fleet-health, and per-engine monitors:

```bash
./deploy/demo/launch.sh
```

---

## Documentation

- [Architecture](./docs/ARCHITECTURE.md) — system design, topology, data flow
- [Metrics reference](./docs/METRICS.md) — every metric, unit, attribute
- [Integration guide](./docs/INTEGRATION.md) — PromQL, OTel Collector recipes, cloud notes
- [K8s workload attribution](./docs/K8S_WORKLOAD_ATTRIBUTION.md) — RBAC, enrichment, label allow-lists
- [Scaling](./docs/SCALING.md) — cardinality management for large fleets
- [GPU & LLM observability](./docs/GPU_LLM_OBSERVABILITY.md) — vLLM / NIM / Triton specifics
- [Helm install](./docs/HELM.md) · [Pre-built collector](./docs/COLLECTOR.md)
- [AWS testing cookbook](./docs/AWS_TESTING.md) — end-to-end EC2 and EKS walk-through
- [`l9gpu` CLI reference](./l9gpu/README.md) · [`slurmprocessor`](./slurmprocessor/README.md) · [`shelper`](./shelper/README.md)

---

## Contributing

PRs welcome. See [`CONTRIBUTING.md`](./CONTRIBUTING.md) for dev setup, tests,
and PR flow. By contributing you agree your work is licensed under the same
terms as the rest of the project. Security reports: [`SECURITY.md`](./SECURITY.md).

## Credits & attribution

`l9gpu` (the Python package), `shelper`, and `slurmprocessor` are derived
from Meta's [facebookresearch/gcm](https://github.com/facebookresearch/gcm)
project (MIT and Apache-2.0). We extended them with Kubernetes workload
attribution, AMD / Intel Gaudi collectors, vLLM / SGLang / TGI / Triton /
NIM monitors, cost and fleet-health signals, and OTLP-native export.
`k8shelper/` and `k8sprocessor/` are original Last9 work. See
[`NOTICE`](./NOTICE) for the full breakdown.

## License

MIT for `l9gpu`, `k8shelper`, `k8sprocessor`. Apache-2.0 for `slurmprocessor`,
`shelper`. Each subdirectory carries its own `LICENSE` where it differs from
the repo root.
