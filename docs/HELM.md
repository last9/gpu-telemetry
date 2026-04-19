# Installing l9gpu via Helm

The chart is published to two registries. Both serve the same artifact.

## Classic Helm repository (GitHub Pages)

```bash
helm repo add l9gpu https://last9.github.io/gpu-telemetry
helm repo update
helm install l9gpu l9gpu/l9gpu -n monitoring --create-namespace
```

## OCI registry (GHCR)

```bash
helm install l9gpu oci://ghcr.io/last9/charts/l9gpu --version 0.1.0 \
  -n monitoring --create-namespace
```

## Listing versions

```bash
helm search repo l9gpu --versions
helm show chart oci://ghcr.io/last9/charts/l9gpu --version 0.1.0
```

## Upgrading / uninstalling

```bash
helm upgrade l9gpu l9gpu/l9gpu -n monitoring --reuse-values
helm uninstall l9gpu -n monitoring
```

---

For OTLP credentials, per-topology values, and configuration options, see
the [main README](../README.md#quick-start--kubernetes) and
[`deploy/helm/l9gpu/examples/`](../deploy/helm/l9gpu/examples).

The chart ships a `values.schema.json` — `helm install` validates your
overrides and IDEs autocomplete against it.
