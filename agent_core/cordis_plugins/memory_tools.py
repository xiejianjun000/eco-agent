#!/usr/bin/env python3
"""
agent_core/cordis_plugins/memory_tools.py — 记忆树 + 策略热更新工具集插件
====================================================================
对标 DSH「工具即插件」：eco_memory_*（记忆树节点管理/检索/遗忘/同步）与
eco_policy_reload（权限策略热更新）从 chat.py 硬编码走向组合装配。
handler 注册进 tools_registry，让 subagent、外部调用方、eco doctor 等
「工具即服务」消费方也能按注册表反查执行；聊天通道 _run_tool 与注册表同源。
"""

from __future__ import annotations

import logging

logger = logging.getLogger("eco.cordis.memory_tools")

_SCHEMAS = {
    "eco_memory_add": {
        "type": "object",
        "properties": {
            "type": {"type": "string", "description": "节点类型 statute/case/benchmark/procedure/session/skill/quality/alert"},
            "title": {"type": "string", "description": "记忆标题"},
            "content": {"type": "string", "description": "记忆正文"},
            "tags": {"type": "array", "items": {"type": "string"}},
            "score": {"type": "number", "description": "重要性 0-100"},
            "parent_id": {"type": "string"},
        },
        "required": ["title", "content"],
    },
    "eco_memory_update": {
        "type": "object",
        "properties": {
            "node_id": {"type": "string"},
            "title": {"type": "string"}, "content": {"type": "string"},
            "score": {"type": "number"}, "tags": {"type": "array", "items": {"type": "string"}},
            "parent_id": {"type": "string"},
        },
        "required": ["node_id"],
    },
    "eco_memory_delete": {
        "type": "object",
        "properties": {"node_id": {"type": "string"}},
        "required": ["node_id"],
    },
    "eco_memory_search": {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "type": {"type": "string"}, "limit": {"type": "integer"},
        },
        "required": ["query"],
    },
    "eco_memory_stats": {"type": "object", "properties": {}, "required": []},
    "eco_memory_prune": {
        "type": "object",
        "properties": {
            "min_score": {"type": "number"}, "max_age_days": {"type": "integer"},
            "dry_run": {"type": "boolean"},
        },
        "required": [],
    },
    "eco_memory_sync": {
        "type": "object",
        "properties": {"mode": {"type": "string", "enum": ["to", "from", "both"]}},
        "required": [],
    },
    "eco_policy_reload": {"type": "object", "properties": {}, "required": []},
}

_DESC = {
    "eco_memory_add": "向记忆树写入一条结构化记忆节点（score/tags/parent_id 树形结构）",
    "eco_memory_update": "更新记忆树节点（标题/内容/评分/标签/父节点）",
    "eco_memory_delete": "删除记忆树节点（子节点自动提升为根节点）",
    "eco_memory_search": "检索记忆树（BM25 + 向量混合检索，中文降级）",
    "eco_memory_stats": "记忆树统计：节点数/边数/类型分布",
    "eco_memory_prune": "记忆树遗忘维护（低分/长期未访问清理，security/denied 受保护，dry_run 预览）",
    "eco_memory_sync": "记忆树与 Obsidian 双向同步（to/from/both）",
    "eco_policy_reload": "热重载权限策略（PERMISSION.md 工具风险覆盖 + L3 白名单，免重启）",
}

_LEVEL = {
    "eco_memory_add": "L2", "eco_memory_update": "L2", "eco_memory_delete": "L2",
    "eco_memory_search": "L1", "eco_memory_stats": "L1", "eco_memory_prune": "L2",
    "eco_memory_sync": "L2", "eco_policy_reload": "L1",
}


def apply(ctx, config: dict | None = None) -> None:
    """组合装配入口：注册记忆树/策略热更新工具 handler（幂等）。"""
    from agent_core.tools_registry import register_external_tool, _HANDLERS
    from agent_core.memory_tools import dispatch_memory_tool

    registered: list[str] = []
    for name, schema in _SCHEMAS.items():
        if name in _HANDLERS:
            continue  # 幂等跳过
        try:
            register_external_tool(
                name, _DESC[name], schema,
                (lambda n: (lambda **kw: dispatch_memory_tool(n, kw)))(name),
                risk_level=_LEVEL[name], source="memory_tree")
            registered.append(name)
        except Exception as e:  # noqa: BLE001 — 幂等注册
            logger.debug("[memory_tools] %s 注册跳过: %s", name, e)
    logger.info("[memory_tools] 组合装配注册 %d 个记忆/策略工具: %s",
                len(registered), registered)
