---
name: release-engineering
description: End-to-end release of a Python package (CLI / MCP server / skill pack) to GitHub, PyPI, and ecosystem aggregation lists — naming & availability checks, local packaging, GitHub repo creation + tag + topics, twine upload, clean-venv verification, and awesome-list pull requests. Use when publishing a new package, re-releasing a version, or on-boarding a repository into DeepSeek Harness / MCP / awesome ecosystems. Python 包（CLI / MCP server / 技能包）的端到端发布流程：发布到 GitHub、PyPI 与生态合集列表——命名与占用检查、本地打包、GitHub 建仓 + tag + topics、twine 上传、干净 venv 验证、awesome 列表 PR。发布新包、重新发版本或把仓库收录进 DeepSeek Harness / MCP / awesome 生态时使用。
keywords: [release, publish, pypi, github, twine, pip, mcp, packaging, 发布, 打包, 分发]
---
# Release Engineering

Publish a Python distribution to GitHub + PyPI and get it listed in ecosystem aggregation repos (awesome lists), end to end. This flow was proven across three real releases in one day — a CLI+MCP audit tool, an MCP server, and a data-only skill pack.

## Flow Overview

```
Check names (PyPI + GitHub)
  → local packaging (pyproject, extras, data-files)
  → GitHub: create repo → push main + tag → set topics
  → PyPI: python -m build → twine upload
  → verify in a clean venv (CLI smoke + MCP handshake)
  → awesome-list PR (fork → sync → branch → bilingual entry)
```

## Prerequisites

- **`GH_PAT_TOKEN`** — classic PAT, `repo` scope, stored as a Machine-scoped env var. Fine-grained PATs often lack `create repo` permission (403 on `POST /user/repos`) — if repo creation fails with 403, check the PAT type first.
- **`PYPI_TOKEN`** — PyPI API token, Machine-scoped env var, starts with `pypi-`.
- **Never print token values.** Read them into variables, pass via env vars, strip them from git remotes after pushing.
- Python 3.11+ for building; the verify venv must match the package's `requires-python` (see Pitfall 3).

## Step 0 — Names: check availability before you commit to anything

A name that is free on GitHub may be taken on PyPI, and vice versa.

```powershell
# PyPI availability (404 = free)
try { (Invoke-RestMethod -Uri "https://pypi.org/pypi/<name>/json").info.version; "TAKEN" } catch { "FREE" }
# GitHub availability
try { (Invoke-RestMethod -Uri "https://api.github.com/repos/<owner>/<name>" -Headers @{Authorization="Bearer $tok"}).full_name; "TAKEN" } catch { "FREE" }
```

**Conventions** (proven in the DSH ecosystem):
- Prefix packages with the ecosystem: `dsh-<thing>` (`dsh-repo-health`, `dsh-kanban-mcp`, `dsh-engineering-skills`).
- The **PyPI distribution name and the GitHub repo name should match** — it makes install docs and repo lookups unambiguous.
- If PyPI is taken but GitHub is free, rename the distribution only and **keep the CLI command name** (console script names are decoupled from distribution names — see Pitfall 2).

## Step 1 — Local packaging (pyproject.toml)

- `[build-system]`: `setuptools>=75.0` + `wheel`, backend `setuptools.build_meta`.
- `readme = "README.md"` — the README renders on the PyPI page; keep it accurate.
- `requires-python`: set the real floor (`tomllib` needs 3.11+; 3.10-only code can advertise 3.10). This gates installs on old Pythons — deliberately.
- Optional dependencies as extras: `mcp = ["fastmcp>=2.0"]`, `dev = ["pytest>=8.0.0"]`. FastMCP is the standalone `fastmcp` package on modern mcp SDKs; if code must also run on mcp SDK 1.x, fall back to `mcp.server.fastmcp` at import time.
- `[project.scripts]`: one entry per CLI, `name = "module:main"`.
- src-layout (`where = ["src"]`) keeps the wheel clean.
- `.gitignore`: `dist/`, `build/`, `*.egg-info/`, `.pytest_cache/`, `.venv/` — never commit build artifacts.

### Packaging a data-only skill pack (markdown files, no code)

The wheel must carry the markdown, and the CLI must find it after install. Proven approach — `data-files`:

```toml
[tool.setuptools.data-files]
"share/<dist>/skills/<skill-one>" = ["skills/<skill-one>/SKILL.md"]
"share/<dist>/skills/<skill-two>" = ["skills/<skill-two>/SKILL.md"]
```

- CLI resolution order: repo checkout `skills/` (editable install) → `sysconfig.get_path("data")/share/<dist>/skills` (wheel install).
- **Pitfall 1 (data-files glob)**: `"share/.../skills" = ["skills/*/SKILL.md"]` **flattens paths to the basename** — five `SKILL.md` files collide and only one survives in the wheel. List each skill as its own target directory, explicitly. Verify the wheel contents before uploading:
  ```powershell
  python -c "import zipfile,glob; [print(n) for z in glob.glob('dist/*.whl') for n in zipfile.ZipFile(z).namelist() if 'SKILL' in n or 'share' in n]"
  ```
- `MANIFEST.in` for the sdist: `recursive-include skills *.md`.

## Step 2 — GitHub release

```powershell
$tok = [System.Environment]::GetEnvironmentVariable("GH_PAT_TOKEN", "Machine")
# 1. create repo (public + description)
Invoke-RestMethod -Method Post -Uri "https://api.github.com/user/repos" `
  -Headers @{Authorization="Bearer $tok"; Accept="application/vnd.github+json"} `
  -ContentType "application/json" `
  -Body (@{name="<repo>"; description="<desc>"; private=$false} | ConvertTo-Json)
# 2. push main + tag via token URL, then strip the token from the remote
git remote add origin "https://x-access-token:${tok}@github.com/<owner>/<repo>.git"
git push origin main
git tag v0.1.0 && git push origin v0.1.0
git remote set-url origin "https://github.com/<owner>/<repo>.git"
# 3. topics (must be lowercase; spaces become '-' internally)
Invoke-RestMethod -Method Put -Uri "https://api.github.com/repos/<owner>/<repo>/topics" `
  -Headers @{Authorization="Bearer $tok"; Accept="application/vnd.github+json"} `
  -ContentType "application/json" `
  -Body (@{names=@("dsh-plugin","dsh","mcp-server","deepseek-harness")} | ConvertTo-Json)
```

## Step 3 — PyPI upload

```powershell
python -m pip install build twine
python -m build                       # sdist + wheel into dist/
$env:TWINE_USERNAME = "__token__"
$env:TWINE_PASSWORD = [System.Environment]::GetEnvironmentVariable("PYPI_TOKEN", "Machine")
python -m twine upload --non-interactive --disable-progress-bar dist/*
```

Environment variables keep the token out of shell history and out of process listings.

## Step 4 — Verify from PyPI, not from the working tree

The only proof that the release works is installing the *uploaded artifact* in a clean environment.

```powershell
py -3.13 -m venv C:\Temp\verify_venv
& C:\Temp\verify_venv\Scripts\python -m pip install "<dist>" "<dist>[mcp]"   # as a user would
& C:\Temp\verify_venv\Scripts\<cli> --help                                    # CLI smoke
# MCP servers: stdio handshake and list tools (--help is NOT a valid arg for an MCP server)
```

- **Pitfall 2 (CLI name vs distribution name)**: renaming the PyPI distribution does not rename the console script. `dsh-repo-health` installs the command `repo-health` — README examples keep working after a rename.
- **Pitfall 3 (verify venv Python)**: if `requires-python >= 3.11`, a 3.10 venv fails with `ERROR: Ignored ... Requires-Python >=3.11` and "No matching distribution found" — the package is fine, the venv is too old. Match the venv to the floor.
- For MCP servers, probe tools over stdio (initialize → list_tools) and confirm the expected tool names/count.

## Step 5 — Aggregation-list PR (awesome repos)

One PR per repo, one change per PR, bilingual README entry.

```powershell
# from a fork of the awesome repo:
git fetch upstream && git merge upstream/main   # sync before branching
git checkout -b add-<repo>
# edit README: add one line in the right category
#   EN: - [owner/repo](url) — description.
#   CN: add a second line with " —— " (Chinese description)
git push origin add-<repo>
# open PR via https://github.com/<owner>/awesome-<x>/compare (or the API)
```

- Check the list's inclusion rules first: some lists require a `dsh-plugin` topic (loose gate), others require a `dsh.bundle` declaration in `package.json` (hard gate — pure MCP servers cannot enter those lists, only native Cordis/TS plugins can).
- Tell the maintainer what changed and why it belongs; keep the diff minimal.

## Release checklist

- [ ] PyPI + GitHub names checked; distribution renamed if taken; CLI name unchanged
- [ ] `python -m build` clean; wheel contents inspected (data-files present, no flattening)
- [ ] `dist/`/`build/`/`*.egg-info` ignored by git
- [ ] GitHub repo public, main + tag pushed, topics set
- [ ] twine upload OK; PyPI page shows correct README + version
- [ ] Clean venv (correct Python floor): install + CLI smoke + MCP tool list
- [ ] awesome PR opened (one repo per PR, bilingual entry, category correct)
- [ ] Docs updated: plan/milestone doc, session memory (file:line style), local git commits with explicit paths
