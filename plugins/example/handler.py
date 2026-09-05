#!/usr/bin/env python3
"""
plugins/example/handler.py — 示例插件生命周期入口

演示：load(ctx) 注册工具 / unload(ctx) 清理 / PluginContext API。
"""

from __future__ import annotations

# ── 工具实现 ─────────────────────────────────────────────


def _echo(text: str) -> str:
    return text


def _case_digest(title: str, facts: str) -> str:
    """案卷要点摘要（演示用）。"""
    summary = " ".join(facts.replace("\n", " ").split())[:200]
    return f"[{title}] 要点: {summary}"


# ── 生命周期 ─────────────────────────────────────────────


def load(ctx):
    ctx.register_tool("example_echo", _echo, description="回显输入的文本", risk_level="L1")
    ctx.register_tool("example_case_digest", _case_digest, description="案卷要点摘要（演示 L3 工具）", risk_level="L3")
    ctx.log("example plugin loaded")
    return {"ok": True, "tools": sorted(ctx.tools.keys())}


def unload(ctx):
    ctx.log("example plugin unloaded")
    return {"ok": True}
