# Maintainer Guide: Releasing & Publishing

This internal guide details how the versioning, GitHub Releases, and PyPI distribution pipelines operate for `parallels-pro-mcp-server`.

---

## 1. Architecture Overview

```
[ Git Tag: v0.2.0 ] 
       │  (git push origin v0.2.0)
       ▼
[ GitHub Actions: .github/workflows/release.yml ]
       │
       ├─► 1. Install Python ($PYTHON_VERSION, default: 3.12)
       ├─► 2. Build Wheel & Sdist (uv build)
       ├─► 3. Create GitHub Release with auto-changelog & asset uploads
       └─► 4. Negotiate OIDC Token with PyPI (Trusted Publishing)
             │
             ▼
       [ PyPI Package Registry: parallels-pro-mcp-server ]
             │
             ▼
       [ End Users: uvx parallels-pro-mcp-server ]
```

### Why No API Keys or Secrets Are Required
We use **PyPI Trusted Publishing** via OpenID Connect (OIDC). When a workflow job running in the `pypi` environment executes, GitHub Actions issues a short-lived cryptographic token confirming the job originated from `PopBot/parallels-pro-mcp-server` under workflow `release.yml`. PyPI validates this token and accepts the package upload without requiring long-lived API tokens or passwords.

---

## 2. One-Time Setup: PyPI Trusted Publishing

Before cutting the very first automated release, link the GitHub repository to PyPI:

### Step A: Configure Pending Publisher on PyPI
1. Log in to [pypi.org](https://pypi.org).
2. Navigate to **Account Settings** -> **Publishing** ([pypi.org/manage/account/publishing/](https://pypi.org/manage/account/publishing/)).
3. Under **Add a new pending publisher**, select **GitHub**.
4. Fill in the exact fields:
   - **PyPI Project Name**: `parallels-pro-mcp-server`
   - **Owner**: `PopBot`
   - **Repository Name**: `parallels-pro-mcp-server`
   - **Workflow name**: `release.yml`
   - **Environment name**: `pypi`
5. Click **Add**.

### Step B: Create GitHub Environment
1. In the GitHub repository, go to **Settings** -> **Environments**.
2. Click **New environment** and enter the name `pypi`.
3. (Optional) Under **Deployment branches and tags**, select **Selected tags** with pattern `v*`.

---

## 3. Step-by-Step Release Runbook

Follow these steps to publish a new release:

### 1. Pre-Flight Verification
Run all tests and coverage checks locally:
```bash
# Verify test suite and coverage
uv run coverage run --source=parallels_mcp -m unittest discover -s tests
uv run coverage report -m

# Run doctor diagnostic
uv run parallels-pro-mcp doctor
```

### 2. Update Changelog and Bump Version
1. Open `CHANGELOG.md` and move all items from `## [Unreleased]` into a new version header:
   ```markdown
   ## [0.3.0] - 2026-09-25
   ```
   Keep an empty `## [Unreleased]` section at the top for future contributions.

2. Open `parallels_mcp/__init__.py` and bump `__version__`:
   ```python
   __version__ = "0.3.0"
   ```

### 3. Commit and Push to Main
```bash
git add CHANGELOG.md parallels_mcp/__init__.py
git commit -m "chore: release 0.3.0"
git push origin main
```

### 4. Create and Push the Git Tag
```bash
git tag v0.2.0
git push origin v0.2.0
```

### 5. Monitor Workflow Execution
1. Open the [GitHub Actions page](https://github.com/PopBot/parallels-pro-mcp-server/actions/workflows/release.yml).
2. The `Release & Publish` workflow will trigger automatically.
3. The job will:
   - Build `parallels_pro_mcp_server-0.2.0.tar.gz` and `parallels_pro_mcp_server-0.2.0-py3-none-any.whl`.
   - Publish the release to GitHub Releases with downloadable assets.
   - Publish the release to PyPI.

---

## 4. Post-Release Verification

1. **Verify GitHub Release**:
   Visit `https://github.com/PopBot/parallels-pro-mcp-server/releases` to verify the tag, release notes, and attached assets.
2. **Verify PyPI**:
   Visit `https://pypi.org/project/parallels-pro-mcp-server/` to verify the package version and README rendering.
3. **Verify Global Installation via uvx**:
   In any terminal outside the repo:
   ```bash
   uvx parallels-pro-mcp-server doctor
   ```

---

## 5. Changing the Python Publishing Version

The release workflow is parameterized with a top-level environment variable in `.github/workflows/release.yml`:

```yaml
env:
  PYTHON_VERSION: ${{ inputs.python_version || '3.12' }}
```

- **Permanent change**: Change `'3.12'` at the top of `.github/workflows/release.yml`.
- **Ad-hoc manual run**: Go to GitHub Actions -> `Release & Publish` -> **Run workflow**, and type any Python version (e.g. `3.13`) into the input box.

---

## 6. Important PyPI Rules & Troubleshooting

- **Immutable Releases**: PyPI strictly forbids overwriting or re-uploading an existing version. If a release contains a critical flaw, do not attempt to delete and re-upload the same version number. Instead, fix the bug, bump the patch version (e.g. `0.2.1`), and push a new tag `v0.2.1`.
- **Wheel Universality**: Because this package is pure Python without compiled C/Rust extensions, the wheel built is universal (`py3-none-any.whl`). It will run identically on any platform (macOS Intel, Apple Silicon) on Python 3.10 through 3.14+.
