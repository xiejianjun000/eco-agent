---
name: ci-diagnosis-and-fix
description: Diagnose and fix GitHub Actions CI when workflows turn systematically red — systematic triage and repair flow for pipeline failures. Use when CI is failing wholesale, when asked to fix pipeline/action errors, or when reviewing workflow configurations. 诊断并修复 CI 系统性变红的 GitHub Actions 工作流——管道失败的系统化分流与修复流程。当 CI 批量失败、要求修复 pipeline/action 错误或审查工作流配置时使用。
keywords: [ci, pipeline, github, action, workflow, build, 流水线, 构建, "github actions"]
---
# CI Failure Diagnosis & Repair

When GitHub Actions CI turns systematically red, triage and fix it with this flow instead of patching workflows one at a time.

## Flow Overview

```
Trigger (failed run notification / manual request)
  → find the workflow run via the GitHub API
  → pull the failing job's log
  → classify the root cause
  → fix
  → verify
```

## Prerequisites

- **GitHub Token** with `repo` + `workflow` + `actions: read` permissions (a classic PAT with `repo` scope suffices).

## Diagnosis Flow (Step-by-Step)

### 1. Find the failing workflow run

```
GET /repos/{owner}/{repo}/actions/runs?per_page=10&status=failure
```

Use the token as a Bearer token. Focus on `run_number`, `name`, `head_branch`, `conclusion`, `html_url`. Prefer the most recent run on the branch you care about; check whether multiple workflows failed on the *same commit*.

### 2. Find the failing job

```
GET /repos/{owner}/{repo}/actions/runs/{run_id}/jobs
```

Walk `jobs[].steps[]` and locate the step with `conclusion == "failure"`.

### 3. Download the failing step's log

```
GET /repos/{owner}/{repo}/actions/runs/{run_id}/logs
```

Returns a zip; extract **only** the failing step's log, not everything (logs can be huge). Decode with `utf-8-sig` (GitHub logs carry a BOM). Read the last 2000–3000 characters of the failing step.

### 4. Classify the root cause

| Error signature | Common root cause | Fix direction |
|---|---|---|
| `No matching distribution found for X` | dependency version does not exist / incompatible | pin a released version or bump the CI Python |
| `ModuleNotFoundError` | missing dependency / wrong import path | add the dependency or fix the import |
| `assert ... failed` / red tests | code logic | fix the code |
| `Process completed with exit code 1` (no clear error) | environment / timeout | read the full log |
| `SyntaxError` / `TypeError` | Python version incompatibility | fix code or align versions |
| `Timeout` | slow tests / network | raise the timeout or fix the slow path |

**Multiple workflows failing at the same time on the same commit → almost always a dependency/environment problem, not code.** One broken shared dependency cascades into "everything red".

### 5. Compare history

Repeated failures on the same branch over many runs → a persistent problem, not a flake. Check whether the last ~30 failed runs cluster on a specific commit range (a single broken merge).

## Common Fixes

### GITHUB_OUTPUT delimiter syntax

The old `echo "k=v" >> "$GITHUB_OUTPUT"` syntax fails on newer runners (`Invalid format`). Use the delimiter form, which works everywhere:

```bash
# Old (fails on Node 24 runners)
echo "count=$ERROR_COUNT" >> "$GITHUB_OUTPUT"

# New (delimiter syntax)
echo "count<<EOF" >> "$GITHUB_OUTPUT"
echo "$ERROR_COUNT" >> "$GITHUB_OUTPUT"
echo "EOF" >> "$GITHUB_OUTPUT"
```

### Playwright E2E — let webServer manage the dev server

If `playwright.config.ts` already declares a `webServer`, do NOT start the app separately in the workflow — Playwright manages it.

```yaml
- name: Install Playwright browsers
  run: npx playwright install chromium --with-deps
- name: Run Playwright tests   # Playwright auto-starts webServer
  run: npx playwright test
  env:
    CI: "true"
```

### Dependency files — surgical edits only

Rewrite only the offending line, never the whole file. `git show HEAD:requirements.txt` gives you the original; a full rewrite loses version pins and indirect dependencies.

## Verification after a fix

1. `pip install -r requirements.txt --dry-run` — confirm the dependency set resolves
2. Grep every workflow that uses `$GITHUB_OUTPUT` and confirm it uses the delimiter form
3. Confirm no duplicate dev-server starts / port conflicts (Playwright webServer vs manual start)

## Notes

- **Encoding**: Windows consoles default to cp1252; avoid `✗✓★◆` etc. in `print()` output, use `[FAIL]` / `[OK]` ASCII markers.
- **BOM**: GitHub log zips carry a UTF-8 BOM (`\ufeff`); decode with `utf-8-sig`.
- **Token scope**: pulling logs requires `repo` + `workflow` (`actions: read`).
- **Batch failure pattern**: many workflows red at the same commit ⇒ dependency/environment issue, not N separate code bugs.
