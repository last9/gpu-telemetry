# Runtime image for l9gpu-collector.
#
# Expects the binary at l9gpu-collector in the build context — goreleaser
# provides it via its docker config. For local builds, run ocb first:
#   builder --config deploy/collector/builder-config.yaml
#   docker build -f deploy/collector/Dockerfile -t l9gpu-collector .

FROM gcr.io/distroless/static-debian12:nonroot

COPY l9gpu-collector /l9gpu-collector

USER nonroot:nonroot

ENTRYPOINT ["/l9gpu-collector"]
