# l9gpu-collector

Pre-built OpenTelemetry Collector distribution bundling:

- Standard OTLP receivers/exporters
- `batch`, `memorylimiter`, `k8sattributes`, `resource` processors
- **`k8sprocessor`** — per-GPU pod attribution (this repo)
- **`slurmprocessor`** — Slurm job enrichment (this repo)
- `healthcheck` + `zpages` extensions
- `prometheus` receiver (for scraping DCGM exporter, NIM, vLLM, etc.)

Shipped as a single container image and a set of signed tarballs.

---

## Install

### Docker

```bash
docker run --rm \
  -v $PWD/config.yaml:/etc/l9gpu/config.yaml:ro \
  -p 4317:4317 -p 4318:4318 \
  ghcr.io/last9/l9gpu-collector:latest
```

Use `:latest` for tracking the newest release, or pin to a version:

```bash
docker pull ghcr.io/last9/l9gpu-collector:collector-v0.1.0
```

Multi-arch (linux/amd64, linux/arm64). Docker picks the right image
automatically.

### Kubernetes

Deploy as a Deployment or DaemonSet. Point the image at
`ghcr.io/last9/l9gpu-collector` and mount your config from a ConfigMap
at `/etc/l9gpu/config.yaml` (or wherever `--config` points).

### Binary (Linux / macOS)

Tarballs are attached to every GitHub release:

```bash
VERSION=v0.1.0
OS=linux       # or darwin
ARCH=amd64     # or arm64

curl -sSLO https://github.com/last9/gpu-telemetry/releases/download/collector-${VERSION}/l9gpu-collector_${VERSION#v}_${OS}_${ARCH}.tar.gz
tar -xzf l9gpu-collector_${VERSION#v}_${OS}_${ARCH}.tar.gz
./l9gpu-collector --config=config.yaml
```

---

## Config

A complete working example is in
[`deploy/collector/config.example.yaml`](../deploy/collector/config.example.yaml).

Minimum viable config:

```yaml
receivers:
  otlp:
    protocols:
      grpc: {endpoint: 0.0.0.0:4317}
      http: {endpoint: 0.0.0.0:4318}

processors:
  k8sattributes: {}
  k8s: {}
  batch: {}

exporters:
  otlp:
    endpoint: ${env:OTEL_EXPORTER_OTLP_ENDPOINT}
    headers:
      Authorization: ${env:OTEL_EXPORTER_OTLP_HEADERS}

service:
  pipelines:
    metrics:
      receivers: [otlp]
      processors: [k8sattributes, k8s, batch]
      exporters: [otlp]
    logs:
      receivers: [otlp]
      processors: [k8sattributes, k8s, batch]
      exporters: [otlp]
```

---

## Building from source

If you need a different component set, edit
[`deploy/collector/builder-config.yaml`](../deploy/collector/builder-config.yaml)
and rebuild with [`ocb`](https://github.com/open-telemetry/opentelemetry-collector/tree/main/cmd/builder):

```bash
go install go.opentelemetry.io/collector/cmd/builder@v0.126.0
builder --config deploy/collector/builder-config.yaml
./_build/l9gpu-collector --config=config.yaml
```

---

## Why ship a pre-built distribution?

The OTel-standard way to get custom processors into a collector is for
every user to run `ocb` with their own manifest. That's correct for
advanced users but a poor first experience:

- Requires the Go toolchain
- Requires understanding `ocb` semantics
- Produces an untested binary

Shipping a pre-built distribution — same pattern as Grafana Alloy, Splunk
OTel Collector, AWS ADOT — gives new users a `docker run` on-ramp while
advanced users can still roll their own with the builder-config in this
repo.
