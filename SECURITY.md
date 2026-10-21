# Security Policy

## Reporting a Vulnerability

If you discover a security issue in l9gpu, please report it privately rather
than opening a public GitHub issue.

**Email:** `support@last9.io`

Please include:

- A description of the issue and its impact
- Steps to reproduce
- Affected version(s) and component (`l9gpu`, `k8sprocessor`,
  `slurmprocessor`, `k8shelper`, `shelper`, Helm chart, alerts)
- Any suggested mitigation

## Response Timeline

- We will acknowledge receipt within 3 business days.
- We aim to provide an initial assessment within 10 business days.
- Coordinated disclosure: we request a 90-day embargo from report date to
  public disclosure, extendable by mutual agreement for complex issues.

## Scope

In scope:

- Code in this repository (Python package, Go modules, Helm chart, deployment
  manifests)
- Official container images published from this repo

Out of scope:

- Third-party dependencies (please report upstream; we will bump when a patch
  lands)
- Vulnerabilities requiring physical access to GPU nodes or root on the host

Thank you for helping keep the project and its users safe.

## eMudhra trust-store updates (October 2026)

Python installations require `certifi>=2026.10.19`. The development lockfile
also includes patched `pip>=26.2.2`, which carries its own CA bundle. Go
modules and collector builds require Go 1.27.3 or newer. See the
[incident and patched-version list](https://emudhra.we-have-a-problem.com/)
and the [Go security announcement](https://groups.google.com/g/golang-announce/c/66pojueaQek).

After installing the locked dependencies, run this network smoke check:

```bash
python scripts/check_tls_trust.py
```

It must accept a trusted HTTPS endpoint and reject both the direct and
cross-signed compromised test chains with certificate verification errors.
Connection failures do not count as successful rejection. Add `--system` to
check the host or container system CA bundle too.

Rebuild Python and collector release artifacts with the updated dependencies
and Go compiler before publishing a new release. Rebuild container images
with `--pull --no-cache` to refresh base-image CA bundles and dependency
layers; existing images and installed packages do not receive these changes
automatically. The Python image refreshes Debian's `ca-certificates` package
in both stages. Verify a rebuilt Python image before publishing:

```bash
docker build --pull --no-cache -f docker/Dockerfile -t l9gpu:tls-check .
docker run --rm --entrypoint python \
  -v "$PWD/scripts:/checks:ro" l9gpu:tls-check \
  /checks/check_tls_trust.py --system
```

Publish rebuilt packages and images through the normal release workflows.
Do not disable certificate verification to restore connectivity.
