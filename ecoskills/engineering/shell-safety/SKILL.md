---
name: shell-safety
description: 'Prevent interactive CLI commands from freezing agent sessions. Hard ban on interactive commands (more/less/pause/choice/start /WAIT) with non-interactive equivalents, a mandatory timeout rule, and a pre-flight checklist. Use when running shell commands, diagnosing hangs, or choosing safe CLI alternatives. 防止交互式命令冻结 agent 会话，提供安全替代。'
keywords: [shell, safety, command, sandbox, 安全, 命令]
---
# Shell-Safety

## Overview

Prevent interactive CLI commands from freezing agent sessions. When running inside a headless shell-execution tool (the subprocess has **no interactive terminal / TTY**), commands that wait for keyboard input (`more`, `less`, `pause`, `choice`, `start /WAIT`) will block forever, freezing the calling agent until the process is killed externally.

This skill enforces a hard ban on interactive commands and provides non-interactive equivalents for every common use case.

## Ban List (NEVER use these)

| Command / Pattern    | Why banned                          |
|----------------------|-------------------------------------|
| `more`               | Paginates, waits for keypress       |
| `more.com`           | Same as `more` (explicit extension) |
| `less`               | Paginates, waits for keypress       |
| `pause`              | "Press any key to continue..."      |
| `choice`             | Interactive menu prompt             |
| `start /WAIT app`    | Waits for GUI window to close       |
| `cmd ... \| more`    | Pipe into pager = indefinite block  |
| `* \| more +N`       | Skip-N pager variant, same effect   |

**Any command that requires human interaction is forbidden in a headless agent shell.** Assume the shell has no keyboard or display.

## Safe Replacements

### Counting matches / lines

```cmd
:: Banned
findstr /i "pattern" file | more +0 | find /c "pattern"

:: Correct (native find /c)
findstr /i "pattern" file | find /c /v ""
```

```powershell
# Single line counting
(Select-String -Path file -Pattern 'pattern').Count
```

### Viewing output (non-interactive full dump)

```cmd
:: Banned
type file | more
more file

:: Correct
type file
```

### Pause / confirmation — NEVER use in scripts run by agents

```cmd
:: Banned
pause

:: Correct: just skip it. The agent doesn't need human confirmation mid-script.
rem (remove the pause entirely)
```

### Waiting for external processes

```cmd
:: Banned
start /WAIT notepad.exe

:: Correct: timeout-controlled wait for known processes
timeout /T 10 /NOBREAK
tasklist | findstr processname
```

## Timeout Rule (MANDATORY)

Every shell call MUST include a timeout. This is the hard kill switch:

```text
run_shell(command="...", timeout_ms=60000)   # 60s max
```

- Short lookups (findstr on small files): `timeout_ms=15000`
- Medium scans (grep on <100 files): `timeout_ms=30000`
- Long commands (builds, tests): `timeout_ms=300000` (5 min)
- Never omit the timeout. The default is "wait forever" — exactly what you're preventing.

## Pre-Flight Checklist (before every shell call)

1. [ ] No `more`, `less`, `pause`, `choice`, `start /WAIT` anywhere in the command string or pipeline
2. [ ] No `more.com` explicit extension (PATH shims can't intercept it)
3. [ ] A timeout is set and reasonable for the expected runtime
4. [ ] If counting/filtering: use `find /c /v ""` or PowerShell `Select-String` + `.Count` instead of piping through pagers
5. [ ] If viewing output: `type` (Windows) or `cat` (cross-platform) — NEVER pipe to a pager

## Why This Exists

A real incident: an agent session froze for 12+ minutes because the model generated:

```cmd
findstr /i "/api/health" logs\endpoint_hits.jsonl | more +0 | find /c "/api/health"
```

`more +0` waited for keyboard input that would never arrive. The pipe chain blocked, the model waited on its shell tool, and the session appeared dead — the only recovery was externally killing the `findstr` and `more.com` processes.

This skill plus a companion PATH-level shim (which replaces `more`/`less`/`pause` with non-interactive equivalents) form a two-layer defense against this class of bug.
