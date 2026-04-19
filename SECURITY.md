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
