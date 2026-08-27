#!/usr/bin/env python3
"""
agent_core/inspect.py — Inspect 契约目录（对标 DSH Inspect Provider）

只读目录：服务/插件/工具/槽位/事件 的 name + description + schema，
供模型与调用方在扩展前查询（业务数据不可经此获取——只描述形状）。

与 DSH 的差异（如实声明）：无 input/output JSON Schema 双向契约
（工具参数保留 OpenAI JSON Schema），服务/插件只有 name + 摘要。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("eco.inspect")


def catalog() -> dict:
    """全目录：services/plugins/tools/slots。"""
    return {
        "services": list_services(),
        "plugins": list_plugins(),
        "tools": list_tools(),
        "slots": list_slots(),
    }


def list_services() -> list[dict]:
    out = []
    try:
        from agent_core.cordis.boot import get_app_context

        snap = get_app_context().snapshot()
        for name in snap.get("services", []):
            out.append({"name": name, "description": _SERVICE_DESCRIPTIONS.get(name, "")})
    except Exception as e:  # noqa: BLE001
        logger.warning("inspect services failed: %s", e)
    return out


def list_plugins() -> list[dict]:
    out = []
    try:
        from agent_core.cordis.boot import get_app_context

        snap = get_app_context().snapshot()
        for name, status in snap.get("plugins", {}).items():
            out.append({"name": name, "status": status,
                        "description": _PLUGIN_DESCRIPTIONS.get(name, "")})
    except Exception as e:  # noqa: BLE001
        logger.warning("inspect plugins failed: %s", e)
    return out


def list_tools() -> list[dict]:
    out = []
    try:
        from server.api.chat import _codex_tools

        for tool in _codex_tools():
            fn = tool.get("function", {})
            out.append({
                "name": fn.get("name", ""),
                "description": fn.get("description", ""),
                "schema": fn.get("parameters"),
            })
    except Exception as e:  # noqa: BLE001
        logger.warning("inspect tools failed: %s", e)
    return out


def list_slots() -> list[dict]:
    try:
        from agent_core.slots import get_slot_registry

        return get_slot_registry().list()
    except Exception as e:  # noqa: BLE001
        logger.warning("inspect slots failed: %s", e)
        return []


def query(kind: str, name: str) -> dict:
    """精确查询：kind ∈ services/plugins/tools/slots。"""
    mapping = {
        "services": list_services,
        "plugins": list_plugins,
        "tools": list_tools,
        "slots": list_slots,
    }
    lister = mapping.get(kind)
    if lister is None:
        return {"error": f"未知类别: {kind}（可用: {sorted(mapping)}）"}
    for item in lister():
        if item.get("name") == name:
            return item
    return {"error": f"{kind} 中未找到: {name}"}


# 服务/插件摘要（声明式维护，新服务/插件在此登记）
_SERVICE_DESCRIPTIONS = {
    "lessons": "对话教训仓库：失败特征提取 + 关键词检索注入（自愈闭环）",
    "trace_audit": "govmcp SM3 审计链：五要素入链 + verify 防篡改",
    "subagents": "子代理注册表：spawn/fork/send_message/interrupt/输出流",
    "slots": "Slot 面板注册表：side.tab 挂点 + 面板数据提供器",
    "goals": "跨轮目标仓库：持久化 + 自动延续轮次 + round-limit",
    "llm": "LLM 客户端：provider 路由 + 流式 + 失败重试",
}

_PLUGIN_DESCRIPTIONS = {
    "agent_core.cordis_plugins.subagent_cleaner":
        "定时清理已结束超过 TTL 的子代理（config: ttl_seconds/interval_seconds）",
    "agent_core.cordis_plugins.audit_panel":
        "注册'审计链'侧栏面板（SM3 审计链 verify + 调用统计）",
}
