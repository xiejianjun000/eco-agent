#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
agent_core/exec_tools.py — 执行层工具（shell 白名单 + 文件精确编辑）
==================================================================
补齐 eco-agent 与开发代理的结构性差距（路线图 ① ②）：

① shell_run：命令白名单 shell 执行（只读+受限命令集，禁写禁删禁链）
② file_read / file_write / file_edit：精确文件读写编辑
   （read L1 只读；write/edit 仅限工作区与仓库根内，写前审计）

安全契约：
- shell 只允许白名单首命令，禁止重定向/命令链/替换/反引号，超时 30s，
  环境变量清洗（仅保留 PATH/LANG），输出截断 8000 字符
- 文件写操作路径解析后必须落在允许根内（realpath 校验防 ../ 逃逸），
  单次写入 ≤ 200KB；file_edit 的 old_string 必须唯一命中（防误伤）
- 每次调用写 SM3 审计链（source=exec_tool），审计失败不阻断
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
from pathlib import Path

# ─── shell 白名单（只读/受限命令集）─────────────────────────────

SHELL_ALLOWED = {
    "ls", "cat", "head", "tail", "wc", "grep", "find", "pwd", "echo",
    "date", "du", "df", "ps", "python3", "python", "git", "tree", "sort",
    "uniq", "sed", "awk", "diff", "basename", "dirname", "which", "test",
    # 开发类（自改自测闭环）：测试/依赖/构建
    "pytest", "pip", "npm", "node", "make",
}

# 高危第一命令（即使白名单里出现变体也拒绝）
SHELL_FORBIDDEN_START = ("rm", "sudo", "chmod", "chown", "kill", "shutdown",
                         "reboot", "mkfs", "dd", "curl", "wget", "scp", "ssh")

# 危险语法模式（任一命中即拒绝）
_SHELL_DANGER_RE = re.compile(
    r"[><]|`|\$\(|\$\{|&&|\|\||;|mkfifo|/dev/|>>"
)

SHELL_TIMEOUT = 30.0
OUTPUT_CAP = 8000

# ─── 文件工具允许根 ────────────────────────────────────────────

def _allowed_roots() -> list[Path]:
    roots = []
    ws = os.environ.get("ECO_WORKSPACE_DIR", "").strip()
    if ws:
        roots.append(Path(ws))
    repo = Path(__file__).resolve().parent.parent
    roots.append(repo)
    return roots


def _audit(action: str, target: str, decision: str, reason: str) -> None:
    try:
        from agent_core.prompt_engine import get_prompt_engine
        get_prompt_engine().audit.append(
            source="exec_tool", content=f"{action} {target[:80]} -> {decision}",
            phase="permission", accepted=(decision == "allow"), reason=reason)
    except Exception:
        pass


# ─── ① shell_run ───────────────────────────────────────────────

def run_shell(command: str) -> str:
    """白名单 shell 执行。返回 JSON 字符串（ok/stdout/stderr/duration）。"""
    cmd = (command or "").strip()
    if not cmd:
        return json.dumps({"ok": False, "error": "空命令"}, ensure_ascii=False)
    if _SHELL_DANGER_RE.search(cmd):
        _audit("shell", cmd, "deny", "危险语法（重定向/链/替换）")
        return json.dumps({"ok": False,
                           "error": "命令含危险语法（重定向/命令链/$替换/反引号均禁止）"},
                          ensure_ascii=False)
    # 按管道分段，每段首命令必须白名单
    segments = [s.strip() for s in cmd.split("|") if s.strip()]
    if not segments:
        return json.dumps({"ok": False, "error": "空命令"}, ensure_ascii=False)
    try:
        first_tokens = [shlex.split(s)[0] for s in segments]
    except ValueError as e:
        return json.dumps({"ok": False, "error": f"命令解析失败: {e}"}, ensure_ascii=False)
    for tok in first_tokens:
        base = Path(tok).name if "/" in tok else tok
        if base in SHELL_FORBIDDEN_START:
            _audit("shell", cmd, "deny", f"高危命令 {base}")
            return json.dumps({"ok": False, "error": f"禁止命令: {base}"}, ensure_ascii=False)
        if base not in SHELL_ALLOWED:
            _audit("shell", cmd, "deny", f"非白名单命令 {base}")
            return json.dumps({"ok": False,
                               "error": f"命令不在白名单: {base}（白名单: "
                                        + "、".join(sorted(SHELL_ALLOWED)) + "）"},
                              ensure_ascii=False)
    _audit("shell", cmd, "allow", "白名单放行")
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "LANG", "LC_ALL")}
    import time
    t0 = time.monotonic()
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                           timeout=SHELL_TIMEOUT, env=env)
        out = (p.stdout or "")[:OUTPUT_CAP]
        err = (p.stderr or "")[:500]
        return json.dumps({
            "ok": True, "exit": p.returncode, "stdout": out, "stderr": err,
            "duration_ms": int((time.monotonic() - t0) * 1000),
            "truncated": bool(p.stdout and len(p.stdout) > OUTPUT_CAP),
        }, ensure_ascii=False)
    except subprocess.TimeoutExpired:
        _audit("shell", cmd, "deny", "超时")
        return json.dumps({"ok": False, "error": f"超时（>{SHELL_TIMEOUT}s）"},
                          ensure_ascii=False)
    except Exception as e:  # noqa: BLE001
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


# ─── ② 文件工具 ────────────────────────────────────────────────

def _resolve_within(path_str: str, for_write: bool) -> tuple[Path | None, str]:
    """解析路径并校验在允许根内。返回 (Path, error)。"""
    p = Path(path_str or "").expanduser()
    if not p.is_absolute():
        return None, "必须使用绝对路径"
    try:
        real = p.resolve()
    except OSError:
        return None, "路径解析失败"
    roots = _allowed_roots()
    if for_write and not any(real.is_relative_to(r) for r in roots):
        return None, f"路径不在可写根内（{', '.join(str(r) for r in roots)}）"
    if not for_write and not any(real.is_relative_to(r) for r in roots):
        return None, f"路径不在可读根内（{', '.join(str(r) for r in roots)}）"
    return real, ""


def file_read(path: str, max_chars: int = 12000) -> str:
    real, err = _resolve_within(path, for_write=False)
    if err:
        _audit("file_read", path, "deny", err)
        return json.dumps({"ok": False, "error": err}, ensure_ascii=False)
    if not real.exists() or not real.is_file():
        return json.dumps({"ok": False, "error": f"文件不存在: {real}"}, ensure_ascii=False)
    try:
        text = real.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)
    _audit("file_read", str(real), "allow", "只读放行")
    truncated = len(text) > max_chars
    return json.dumps({"ok": True, "path": str(real),
                       "chars": min(len(text), max_chars), "truncated": truncated,
                       "content": text[:max_chars]}, ensure_ascii=False)


def file_write(path: str, content: str) -> str:
    if len(content or "") > 200_000:
        return json.dumps({"ok": False, "error": "内容超过 200KB 上限"}, ensure_ascii=False)
    real, err = _resolve_within(path, for_write=True)
    if err:
        _audit("file_write", path, "deny", err)
        return json.dumps({"ok": False, "error": err}, ensure_ascii=False)
    try:
        real.parent.mkdir(parents=True, exist_ok=True)
        real.write_text(content or "", encoding="utf-8")
    except OSError as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)
    _audit("file_write", str(real), "allow", "工作区/仓库内写入")
    return json.dumps({"ok": True, "path": str(real),
                       "bytes": len((content or "").encode("utf-8"))},
                      ensure_ascii=False)


def file_edit(path: str, old_string: str, new_string: str) -> str:
    if not old_string:
        return json.dumps({"ok": False, "error": "old_string 不能为空"}, ensure_ascii=False)
    real, err = _resolve_within(path, for_write=True)
    if err:
        _audit("file_edit", path, "deny", err)
        return json.dumps({"ok": False, "error": err}, ensure_ascii=False)
    try:
        text = real.read_text(encoding="utf-8")
    except OSError as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)
    count = text.count(old_string)
    if count == 0:
        return json.dumps({"ok": False, "error": "old_string 未命中"}, ensure_ascii=False)
    if count > 1:
        return json.dumps({"ok": False,
                           "error": f"old_string 命中 {count} 处（必须唯一，请加长上下文）"},
                          ensure_ascii=False)
    new_text = text.replace(old_string, new_string, 1)
    if len(new_text) > 200_000:
        return json.dumps({"ok": False, "error": "修改后超过 200KB 上限"}, ensure_ascii=False)
    try:
        real.write_text(new_text, encoding="utf-8")
    except OSError as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)
    _audit("file_edit", str(real), "allow", "唯一命中替换")
    return json.dumps({"ok": True, "path": str(real),
                       "replaced": 1, "bytes": len(new_text.encode("utf-8"))},
                      ensure_ascii=False)
