# Kubernetes Workload Attribution for GPU Telemetry

This guide explains how to enrich l9gpu metrics and logs with Kubernetes workload identity so
Last9 dashboards can break down GPU usage by pod, namespace, and application label.

---

## Attribution Tiers

### Tier 1 — Node-level (standard, no custom code)

The OpenTelemetry Collector Contrib
[`k8sattributes` processor](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/processor/k8sattributesprocessor)
enriches every metric and log that passes through the collector with attributes sourced from the
Kubernetes API:

| Attribute | Description |
|---|---|
| `k8s.node.name` | Node name (matches `host.name` set by l9gpu) |
| `k8s.cluster.name` | Cluster name (set by `--cluster` flag across all monitors) |
| `cloud.availability_zone` | AZ from node labels (`topology.kubernetes.io/zone`) |
| `cloud.region` | Region from node labels (`topology.kubernetes.io/region`) |

**Limitation**: This tier only resolves node-level attributes. It cannot map a specific GPU
ordinal to the pod consuming it, because the K8s API does not expose that mapping directly.

**Setup**: See [`deploy/helm/l9gpu/examples/eks-otelcol-k8sattributes.yaml`](../deploy/helm/l9gpu/examples/eks-otelcol-k8sattributes.yaml)
for a ready-to-use otel-collector-contrib Helm values file.

---

### Tier 2 — Per-GPU pod attribution (custom, requires `k8sprocessor`)

The `/k8sprocessor/` directory contains a custom Go OpenTelemetry Collector plugin that:

1. Reads `gpu.index` from incoming metric data points
2. Queries the Kubernetes API for pods on the same node with GPU device requests
3. Maps GPU ordinals to pods via the NVIDIA device plugin's `NVIDIA_VISIBLE_DEVICES` environment
   variable or the `nvidia.com/gpu` resource claim
4. Attaches the following attributes to matching data points:

| Attribute | Description |
|---|---|
| `k8s.pod.name` | Pod consuming the GPU |
| `k8s.namespace.name` | Namespace of the pod |
| `k8s.node.name` | Node name |
| `k8s.container.name` | Container within the pod |
| `k8s.job.name` | Batch Job owning the pod (e.g., `bert-finetune-v3`) |
| `k8s.statefulset.name` | StatefulSet owning the pod (e.g., `inference-server`) |
| `k8s.deployment.name` | Deployment owning the pod via ReplicaSet (e.g., `api-server`) |
| `k8s.pod.label.app` | `app` label from the pod spec |
| `k8s.pod.label.<key>` | Any other label configured in the allow-list |

> `k8s.job.name` / `k8s.statefulset.name` / `k8s.deployment.name` are resolved by walking
> `pod.ownerReferences` at collection time (1–2 extra API calls per pod). At most one of
> these will be non-empty for any given pod.

**When to use**: Multi-tenant clusters where you need per-namespace or per-workload GPU billing
and attribution in Last9.

**RBAC requirements**: The collector ServiceAccount needs `get`/`list`/`watch` on `pods` in all
namespaces:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: otelcol-k8s-reader
rules:
  - apiGroups: [""]
    resources: ["pods", "nodes"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["apps"]
    resources: ["replicasets"]
    verbs: ["get"]
  - apiGroups: ["batch"]
    resources: ["jobs"]
    verbs: ["get"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: otelcol-k8s-reader
subjects:
  - kind: ServiceAccount
    name: otel-collector
    namespace: monitoring
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: otelcol-k8s-reader
```

---

## Last9 PromQL Examples

### GPU utilization by namespace (Tier 2)

```promql
avg by (k8s_namespace_name) (
  gpu_utilization{k8s_cluster_name="prod-us-east-1"}
)
```

### Top pods by GPU memory used

```promql
topk(10,
  gpu_memory_used{k8s_cluster_name="prod-us-east-1"}
  * on (k8s_pod_name, k8s_namespace_name) group_left(k8s_pod_label_app)
  kube_pod_labels
)
```

### GPU utilization per app label

```promql
avg by (k8s_pod_label_app) (
  gpu_utilization{k8s_cluster_name="prod-us-east-1", gpu_vendor="nvidia"}
)
```

### Idle GPUs (no workload assigned)

```promql
gpu_utilization{k8s_cluster_name="prod-us-east-1"} == 0
  unless on (gpu_uuid) group_left() kube_pod_container_resource_requests{resource="nvidia_com_gpu"}
```

### SLURM job GPU efficiency (cross-signal correlation via job_id)

```promql
# GPU utilization for a specific job ID
gpu_utilization{job_id="12345", k8s_cluster_name="prod-us-east-1"}
```

### GPU metrics for a specific Kubernetes Job (ML training run)

```promql
# All GPU utilization for a named training job
avg by (gpu_index) (
  gpu_utilization{k8s_job_name="bert-finetune-v3", k8s_cluster_name="prod-us-east-1"}
)
```

### GPU memory usage by Deployment

```promql
avg by (k8s_deployment_name, k8s_namespace_name) (
  gpu_memory_used_percent{k8s_cluster_name="prod-us-east-1"}
)
```

### GPU utilization by StatefulSet

```promql
avg by (k8s_statefulset_name) (
  gpu_utilization{k8s_cluster_name="prod-us-east-1"}
)
```

> **Note**: Last9 supports [high-cardinality](https://last9.io/high-cardinality) attributes (20M series/metric/day).
> All attributes listed above — including `k8s.pod.name`, `gpu.uuid`, `job.id` — are indexed
> at full fidelity without pre-aggregation.

---

## Complete Attribution Picture

After deploying l9gpu with `--cluster <name>` and otel-collector with `k8sattributes`:

### Resource attributes (stable per node)

| Attribute | Source | Example |
|---|---|---|
| `k8s.cluster.name` | l9gpu `--cluster` flag | `"prod-us-east-1"` |
| `gpu.vendor` | l9gpu `--vendor` flag | `"nvidia"` |
| `host.name` | l9gpu (socket.gethostname) | `"gpu-node-1"` |
| `service.name` | l9gpu (hardcoded) | `"l9gpu"` |
| `k8s.node.name` | k8sattributes processor | `"ip-10-0-1-42.ec2.internal"` |
| `cloud.availability_zone` | k8sattributes processor | `"us-east-1a"` |

### Data-point attributes (per GPU / per metric)

| Attribute | Source | Example |
|---|---|---|
| `gpu.index` | l9gpu | `"0"`, `"1"` |
| `gpu.uuid` | l9gpu | `"GPU-0f12ab34-..."` |
| `gpu.model` | l9gpu | `"Tesla T4"` |
| `job.id` | l9gpu (SLURM env) | `"12345"` |
| `job.user` | l9gpu (SLURM env) | `"alice"` |
| `job.partition` | l9gpu (SLURM env) | `"gpu-small"` |
| `k8s.pod.name` | k8sprocessor (Tier 2) | `"training-job-abc"` |
| `k8s.namespace.name` | k8sprocessor (Tier 2) | `"ml-team"` |
| `k8s.node.name` | k8sprocessor (Tier 2) | `"gpu-node-1"` |
| `k8s.container.name` | k8sprocessor (Tier 2) | `"pytorch"` |
| `k8s.job.name` | k8sprocessor (Tier 2) | `"bert-finetune-v3"` |
| `k8s.statefulset.name` | k8sprocessor (Tier 2) | `"inference-server"` |
| `k8s.deployment.name` | k8sprocessor (Tier 2) | `"api-server"` |
| `k8s.pod.label.app` | k8sprocessor (Tier 2) | `"pytorch-trainer"` |
