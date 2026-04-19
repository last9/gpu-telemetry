# Copyright (c) Meta Platforms, Inc. and affiliates.
# Copyright (c) Last9, Inc.
#
# Multi-stage Docker build for Last9 GPU Telemetry Python components.
# Provides both the `l9gpu` monitoring collector and `health_checks` CLI tools.
#
# Build:
#   docker build -f docker/Dockerfile -t l9gpu:latest .
#
# Multi-platform build:
#   docker buildx build -f docker/Dockerfile \
#     --platform linux/amd64,linux/arm64 -t l9gpu:latest .

# ---------------------------------------------------------------------------
# Build stage
# ---------------------------------------------------------------------------
# Build args control optional vendor support.
# AMD:   docker build --build-arg INSTALL_AMD=1 ...
# Gaudi: uses hl-smi CLI directly; no extra Python packages needed.
ARG INSTALL_AMD=0

FROM python:3.10-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Install dependencies first for layer caching.
# Stub out the package so pip can resolve deps from pyproject.toml without the full source.
# _version.py + version.txt are needed for version resolution during the build.
COPY pyproject.toml .
COPY l9gpu/_version.py l9gpu/_version.py
COPY l9gpu/version.txt l9gpu/version.txt
RUN touch l9gpu/__init__.py && \
    pip install --no-cache-dir --prefix=/install ".[k8s]"

# Copy real source and reinstall the package itself (deps already cached above)
COPY l9gpu/ l9gpu/
RUN pip install --no-cache-dir --no-deps --prefix=/install .

# Optional: install AMD amdsmi bindings (requires ROCm to be available at runtime)
ARG INSTALL_AMD
RUN if [ "$INSTALL_AMD" = "1" ]; then \
      pip install --no-cache-dir --prefix=/install "l9gpu[amd]" 2>/dev/null || \
      pip install --no-cache-dir --prefix=/install amdsmi || \
      { echo "ERROR: INSTALL_AMD=1 but amdsmi package could not be installed"; exit 1; }; \
    fi

# ---------------------------------------------------------------------------
# Runtime stage
# ---------------------------------------------------------------------------
FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/usr/local/slurm/bin:${PATH}"

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Create non-root user
RUN groupadd --gid 65532 l9gpu && \
    useradd --uid 65532 --gid l9gpu --shell /usr/sbin/nologin --create-home l9gpu && \
    mkdir -p /tmp/l9gpu && chown l9gpu:l9gpu /tmp/l9gpu

USER 65532:65532
WORKDIR /home/l9gpu

# Verify entry points are available
RUN l9gpu --help > /dev/null 2>&1 && health_checks --help > /dev/null 2>&1

HEALTHCHECK --interval=60s --timeout=5s --retries=3 \
    CMD ["python", "-c", "import l9gpu"]

ENTRYPOINT ["l9gpu"]
CMD ["--help"]
