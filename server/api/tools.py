#!/usr/bin/env python3
"""
server/api/tools.py — 工具目录 API

聚合三源工具目录：
1. govmcp 政务工具注册表（govmcp_tools，100+ 工具，按 category 分组）
2. MCP 连接器（agent_core.mcp_connector，外部 MCP server 工具）
3. 内置工具（agent_core 自注册工具）
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query

logger = logging.getLogger("eco.server.tools")

router = APIRouter()


def _govmcp_catalog() -> list[dict]:
    """govmcp 政务工具目录（懒加载注册，按 category 分组返回）。"""
    try:
        from govmcp_tools import register_all, registry as govmcp_registry

        if govmcp_registry.count() == 0:
            register_all()
        out = []
        for name, tool in sorted(govmcp_registry.tools.items()):
            meta = getattr(tool.handler, "_govmcp_meta", {})
            out.append({
                "source": "govmcp",
                "name": name,
                "description": tool.description,
                "category": meta.get("category", ""),
                "tags": meta.get("tags", []),
                "approval_required": tool.approval_required,
            })
        return out
    except Exception as e:  # noqa: BLE001
        logger.warning("govmcp catalog unavailable: %s", e)
        return []


@router.get("/tools")
async def list_tools(
    source: str | None = Query(default=None, description="工具来源过滤: govmcp / mcp / builtin"),
    q: str | None = Query(default=None, description="名称/描述关键词"),
) -> dict:
    tools = _govmcp_catalog()
    if source and source != "govmcp":
        tools = [t for t in tools if t["source"] == source]
    if q:
        ql = q.lower()
        tools = [
            t for t in tools
            if ql in t["name"].lower() or ql in t["description"].lower()
            or any(ql in tag.lower() for tag in t["tags"])
        ]
    categories: dict[str, int] = {}
    for t in tools:
        cat = t["category"] or "未分类"
        categories[cat] = categories.get(cat, 0) + 1
    return {"count": len(tools), "categories": categories, "tools": tools}


@router.get("/tools/stats")
async def tool_stats() -> dict:
    tools = _govmcp_catalog()
    categories: dict[str, int] = {}
    approval_count = 0
    for t in tools:
        cat = t["category"] or "未分类"
        categories[cat] = categories.get(cat, 0) + 1
        if t["approval_required"]:
            approval_count += 1
    return {"total": len(tools), "categories": categories, "approval_required": approval_count}
