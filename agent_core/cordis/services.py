#!/usr/bin/env python3
"""
agent_core/cordis/services.py — 标准服务注册（存量模块的 cordis 适配层）

不破坏现有直接 import 的用法：服务只是同一单例在 cordis 上下文里的别名，
chat.py 等存量代码可继续 import 使用，也可逐步改为 ctx.get() 消费。
"""

from __future__ import annotations

from agent_core.cordis import Context


def register_standard_services(ctx: Context) -> Context:
    """注册 eco-agent 存量核心模块为标准服务。"""
    from agent_core.goal import get_goal_store
    from agent_core.lessons import get_lesson_store
    from agent_core.slots import get_slot_registry
    from agent_core.subagent import get_subagent_registry
    from agent_core.trace_audit import get_trace_audit

    ctx.provide("lessons", get_lesson_store(), overwrite=True)
    ctx.provide("trace_audit", get_trace_audit(), overwrite=True)
    ctx.provide("subagents", get_subagent_registry(), overwrite=True)
    ctx.provide("slots", get_slot_registry(), overwrite=True)
    ctx.provide("goals", get_goal_store(), overwrite=True)
    try:
        from agent_core.llm_client import get_default_client

        ctx.provide("llm", get_default_client(), overwrite=True)
    except Exception:  # noqa: BLE001 — LLM 客户端初始化可能依赖环境变量
        pass
    return ctx
