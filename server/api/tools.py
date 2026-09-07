#!/usr/bin/env python3
"""
server/api/tools.py — 工具目录 API

数据源：agent_core.tools_registry（内置工具 + 外部注册工具）。

历史：原先聚合 govmcp_tools 政务工具注册表（100+ 工具）。该包已于 2026-09
移除（依赖内网域名与凭证，通用环境不可达），本接口改读 tools_registry，
即 LLM 实际可调用的工具全集——避免目录与真实能力脱节。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query

logger = logging.getLogger("eco.server.tools")

router = APIRouter()


def _tool_catalog() -> list[dict]:
    """当前运行时真实可用的工具目录（来源 tools_registry）。"""
    try:
        from agent_core import tools_registry as tr

        # ALL_TOOL_DEFS 是 OpenAI tools 格式，name/description 从 function 取
        descs = {
            d.get("function", {}).get("name", ""): d.get("function", {}).get("description", "")
            for d in getattr(tr, "ALL_TOOL_DEFS", [])
        }
        sources = getattr(tr, "_EXTERNAL_TOOL_SOURCES", {})
        risks = getattr(tr, "_EXTERNAL_RISK_OVERRIDES", {})
        out = []
        for name in sorted(getattr(tr, "_HANDLERS", {})):
            source = sources.get(name) or ("mcp" if name.startswith("mcp__") else "builtin")
            try:
                category = tr._schema_category(name)
            except Exception:  # noqa: BLE001
                category = ""
            out.append(
                {
                    "source": source,
                    "name": name,
                    "description": descs.get(name, ""),
                    "category": category,
                    "tags": [],
                    # L3/L4 视为需审批（与权限闸门口径一致）
                    "approval_required": risks.get(name, "") in ("L3", "L4"),
                }
            )
        return out
    except Exception as e:  # noqa: BLE001
        logger.warning("tool catalog unavailable: %s", e)
        return []


@router.get("/tools")
async def list_tools(
    source: str | None = Query(default=None, description="工具来源过滤: mcp / builtin / 其他注册源"),
    q: str | None = Query(default=None, description="名称/描述关键词"),
) -> dict:
    tools = _tool_catalog()
    if source:
        tools = [t for t in tools if t["source"] == source]
    if q:
        ql = q.lower()
        tools = [
            t
            for t in tools
            if ql in t["name"].lower() or ql in t["description"].lower() or any(ql in tag.lower() for tag in t["tags"])
        ]
    categories: dict[str, int] = {}
    for t in tools:
        cat = t["category"] or "未分类"
        categories[cat] = categories.get(cat, 0) + 1
    return {"count": len(tools), "categories": categories, "tools": tools}


@router.get("/tools/stats")
async def tool_stats() -> dict:
    tools = _tool_catalog()
    categories: dict[str, int] = {}
    approval_count = 0
    for t in tools:
        cat = t["category"] or "未分类"
        categories[cat] = categories.get(cat, 0) + 1
        if t["approval_required"]:
            approval_count += 1
    return {"total": len(tools), "categories": categories, "approval_required": approval_count}
