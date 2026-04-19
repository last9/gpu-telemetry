# Releasing

l9gpu publishes to PyPI on every `v*.*.*` tag via
[`.github/workflows/release.yml`](../.github/workflows/release.yml). The
workflow uses PyPI [Trusted Publishing][tp] — no API tokens, no secrets.

[tp]: https://docs.pypi.org/trusted-publishers/

---

## One-time setup

These steps are required once, before the first release.

### 1. Create the PyPI project

Trusted publishing requires the project to exist on PyPI first. Do a single
manual upload to claim the name:

```bash
# Build
pip install --upgrade build twine
python -m build

# Upload (requires an account with 2FA enabled)
twine upload dist/*
```

Use the org account (not a personal one). This is the only manual upload
ever required — every future release runs from CI.

### 2. Configure trusted publishing on PyPI

1. Sign in to PyPI and go to `https://pypi.org/manage/project/l9gpu/`
2. Click **Publishing** in the sidebar
3. Under **Add a new pending publisher** (or **Add a new publisher** if the
   project already has releases), fill in:

   | Field | Value |
   |---|---|
   | Publisher | GitHub |
   | PyPI project name | `l9gpu` |
   | Owner | `last9` |
   | Repository name | `gpu-telemetry` |
   | Workflow name | `release.yml` |
   | Environment name | `pypi` |

4. Save.

From this point on, only the `release.yml` workflow running on the `last9/gpu-telemetry`
repo in the `pypi` environment can publish. No tokens are generated or stored.

### 3. Create the `pypi` environment in GitHub

1. In the GitHub repo, go to **Settings → Environments → New environment**
2. Name: `pypi`
3. **Deployment branches and tags** → Selected tags → add rule `v*.*.*`
4. (Optional but recommended) Add **Required reviewers** — publishing to
   PyPI then pauses for manual approval on each tag.
5. Save.

Scoping the environment to tags prevents accidental PyPI uploads from
non-release workflow runs (PRs, branch pushes).

---

## Cutting a release

After the one-time setup, every release is:

```bash
# 1. Update the version
vim l9gpu/version.txt              # e.g., 0.1.0 → 0.2.0

# 2. Commit and push via PR
git checkout -b release-v0.2.0
git commit -am "chore: bump version to 0.2.0"
gh pr create ...                   # wait for CI + merge

# 3. Tag main
git checkout main
git pull
git tag -a v0.2.0 -m "v0.2.0"
git push origin v0.2.0
```

The tag push fires `release.yml`, which:

1. Builds an sdist + wheel from `pyproject.toml`
2. Runs `twine check` to validate metadata
3. Publishes to PyPI via OIDC (no token involved)
4. Creates a GitHub release with auto-generated notes and the built artifacts attached

If you configured **Required reviewers** on the `pypi` environment, the
publish step pauses until approved in the GitHub Actions UI.

---

## Verifying a release

```bash
# PyPI metadata and release page
curl -s https://pypi.org/pypi/l9gpu/json | jq .info.version

# Install from PyPI in a clean venv
python -m venv /tmp/verify && /tmp/verify/bin/pip install l9gpu
/tmp/verify/bin/l9gpu --version
```

---

## Yanking a broken release

You cannot delete a PyPI release — only *yank* it. Yanked versions are
hidden from `pip install l9gpu` (resolvers skip them) but remain installable
by exact version for anyone who already depends on them.

```bash
twine yank l9gpu 0.2.0 --reason "broken wheel; use 0.2.1"
```

Or via the PyPI web UI: project → Releases → version → **Yank**.
