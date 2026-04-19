# Contributing to l9gpu

Thanks for your interest in contributing. This guide covers the dev workflow,
how to run tests, and what we look for in a PR.

## Code of Conduct

This project follows the [Contributor Covenant](./CODE_OF_CONDUCT.md). By
participating you agree to uphold its terms.

## Repository Layout

| Path | What it is |
|---|---|
| [`l9gpu/`](./l9gpu) | Python package — node-level collector + CLI |
| [`k8sprocessor/`](./k8sprocessor) | Go OTel Collector processor (K8s enrichment) |
| [`slurmprocessor/`](./slurmprocessor) | Go OTel Collector processor (Slurm enrichment) |
| [`k8shelper/`](./k8shelper) | Go K8s API helper library |
| [`shelper/`](./shelper) | Go Slurm helper library |
| [`deploy/helm/`](./deploy/helm) | Helm chart |
| [`deploy/demo/`](./deploy/demo) | One-command EKS demo |
| [`dashboards/`](./dashboards) | Pre-built Grafana dashboards |
| [`alerts/`](./alerts) | Prometheus / Grafana alert rules |
| [`docs/`](./docs) | User-facing documentation |

## Development Setup

### Python (l9gpu)

Requires Python 3.10+.

```bash
# Install dev deps and the package in editable mode
pip install -r dev-requirements.txt
pip install -e .

# Install the pre-commit hooks (runs black, isort, flake8, mypy on commit)
pre-commit install
```

### Go (processors and helpers)

Requires Go 1.22+.

Each Go module is self-contained with its own `go.mod`:

```bash
cd k8sprocessor && go mod download
cd slurmprocessor && go mod download
cd k8shelper && go mod download
cd shelper && go mod download
```

## Running Checks

### Python

```bash
make lint       # nox -s lint         (black --check, isort --check, flake8)
make typecheck  # nox -s typecheck    (mypy)
make test       # nox -s tests        (pytest)
make format     # nox -s format       (black, isort)
```

### Go

```bash
cd k8sprocessor   && go test ./...
cd slurmprocessor && go test ./...
cd k8shelper      && go test ./...
cd shelper        && go test ./...
```

### Helm chart

```bash
helm lint deploy/helm/l9gpu
kubectl apply --dry-run=client -f deploy/demo/
```

## Pull Request Process

1. Fork the repo and create a topic branch (`feat/<short-name>`,
   `fix/<short-name>`, `docs/<short-name>`).
2. Make focused commits. Prefer small, reviewable changes.
3. Include tests for new functionality and bug fixes.
4. Run the full check suite locally before opening the PR (`make lint test` +
   relevant `go test`).
5. Update user-facing docs (`docs/*.md`, README, chart values) if behavior or
   configuration changes.
6. Open the PR against `main`. Describe the motivation, what changed, and any
   follow-ups. Link related issues.
7. Sign off your commits with the [Developer Certificate of Origin](https://developercertificate.org/)
   (`git commit -s`). This line is required on every commit:

       Signed-off-by: Your Name <you@example.com>

## Commit Messages

Use [Conventional Commits](https://www.conventionalcommits.org/) prefixes:

- `feat:` — user-visible new capability
- `fix:` — bug fix
- `docs:` — documentation only
- `refactor:` — no behavior change
- `test:` — test additions / changes
- `build:` / `chore:` — tooling, deps, release plumbing

Keep the subject line under 72 characters; put the *why* in the body.

## Reporting Bugs

Use GitHub Issues. Please include:

- What you ran and what you expected
- Actual output (stdout, logs, metrics samples)
- Environment: OS, Python/Go version, Kubernetes version, GPU model + driver
- A minimal reproduction where possible

## Security

Don't open public issues for security reports. See [`SECURITY.md`](./SECURITY.md).
