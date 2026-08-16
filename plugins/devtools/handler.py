#!/usr/bin/env python3
"""
plugins/devtools/handler.py — 通用开发执行工具集

让 ECO AGENT 拥有与 DSH 同类的执行能力：
  shell_run  沙箱执行命令（os_sandbox，L3）
  file_read  读文件（L1）
  file_write 写文件（L2）
  git_status git 仓库状态（L1）

安全：shell_run 走 agent_core.os_sandbox（Linux bwrap 内核隔离 / 降级 rlimit+超时），
全部工具经 L1-L4 权限闸门。
"""

from __future__ import annotations

import subprocess
from pathlib import Path


# ── 工具实现 ─────────────────────────────────────────────

def shell_run(command: str, cwd: str = "", timeout: int = 30) -> str:
    """沙箱执行 shell 命令。"""
    from agent_core.os_sandbox import SandboxPolicy, run_in_sandbox

    policy = SandboxPolicy()
    policy.max_seconds = max(1, min(int(timeout), 300))
    policy.cwd = cwd or None
    cmd = ["/bin/bash", "-lc", command]
    result = run_in_sandbox(cmd, policy=policy)
    return {
        "exit_code": result.returncode,
        "stdout": _truncate(result.stdout or ""),
        "stderr": _truncate(result.stderr or ""),
        "sandbox_mode": getattr(result, "sandbox_mode", "unknown"),
    }


def file_read(path: str, max_chars: int = 20000) -> str:
    """读取文本文件（限制大小防爆上下文）。"""
    p = Path(path).expanduser()
    if not p.is_file():
        return {"error": f"file not found: {path}"}
    data = p.read_text(encoding="utf-8", errors="replace")
    if len(data) > max_chars:
        return data[:max_chars] + f"\n...[截断，共 {len(data)} 字符]"
    return data


def file_write(path: str, content: str) -> str:
    """写入文本文件（覆盖写）。"""
    p = Path(path).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return {"ok": True, "path": str(p), "chars": len(content)}


def git_status(repo_path: str = ".") -> str:
    """git 仓库状态（status + 最近提交）。"""
    p = Path(repo_path).expanduser()
    try:
        status = subprocess.run(
            ["git", "status", "--short", "--branch"], cwd=str(p),
            capture_output=True, text=True, timeout=15)
        log = subprocess.run(
            ["git", "log", "--oneline", "-3"], cwd=str(p),
            capture_output=True, text=True, timeout=15)
        return {
            "status": status.stdout.strip() or status.stderr.strip(),
            "recent_commits": log.stdout.strip(),
        }
    except (subprocess.SubprocessError, OSError) as e:
        return {"error": str(e)}


def _truncate(data: str, limit: int = 12000) -> str:
    return data if len(data) <= limit else data[:limit] + f"\n...[截断，共 {len(data)} 字符]"


# ── 生命周期 ─────────────────────────────────────────────

# OpenAI JSON Schema 定义（注册进 LLM 可见工具表）
TOOL_SCHEMAS = {
    "shell_run": {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "要执行的 shell 命令"},
            "cwd": {"type": "string", "description": "工作目录（可选）"},
            "timeout": {"type": "integer", "description": "超时秒数（默认 30，上限 300）"},
        },
        "required": ["command"],
    },
    "file_read": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径"},
            "max_chars": {"type": "integer", "description": "最大返回字符数（默认 20000）"},
        },
        "required": ["path"],
    },
    "file_write": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径（自动创建父目录）"},
            "content": {"type": "string", "description": "写入内容"},
        },
        "required": ["path", "content"],
    },
    "git_status": {
        "type": "object",
        "properties": {
            "repo_path": {"type": "string", "description": "git 仓库路径（默认当前目录）"},
        },
        "required": [],
    },
}

TOOL_RISK = {"shell_run": "L3", "file_read": "L1", "file_write": "L2", "git_status": "L1"}


def load(ctx):
    ctx.register_tool("shell_run", shell_run, description="在沙箱中执行 shell 命令", risk_level="L3")
    ctx.register_tool("file_read", file_read, description="读取文本文件内容", risk_level="L1")
    ctx.register_tool("file_write", file_write, description="写入文本文件（覆盖）", risk_level="L2")
    ctx.register_tool("git_status", git_status, description="查看 git 仓库状态", risk_level="L1")

    # 注册进 LLM 可见工具表（tools_registry），使模型可在 ReAct 循环中自主选择调用
    from agent_core.tools_registry import register_external_tool

    registered = []
    for name, handler in ctx.tools.items():
        try:
            register_external_tool(
                name=name,
                description=ctx.metadata[name]["description"],
                parameters=TOOL_SCHEMAS[name],
                handler=handler,
                risk_level=TOOL_RISK[name],
                source="devtools",
            )
            registered.append(name)
        except ValueError as e:
            ctx.log(f"tools_registry 注册跳过 {name}: {e}")
    ctx.log(f"devtools plugin loaded: {registered}")
    return {"ok": True, "tools": sorted(ctx.tools.keys()), "model_visible": registered}


def unload(ctx):
    from agent_core.tools_registry import unregister_external_tool

    for name in ctx.tools:
        unregister_external_tool(name)
    ctx.log("devtools plugin unloaded")
    return {"ok": True}
