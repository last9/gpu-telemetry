# gpu-telemetry conventions

## Release builds
- Collector distribution targets Linux only. Do NOT add darwin/windows
  to goreleaser `goos` or collector Dockerfiles — the collector is
  deployed on Linux servers and Kubernetes.
- linux/arm64 docker images are built on native arm64 runners only.
  Do NOT re-enable qemu-based multi-arch docker builds (they time out).
  arm64 binary tarballs via Go cross-compile are fine.
