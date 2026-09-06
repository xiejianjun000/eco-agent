#!/usr/bin/env python3
"""
server/api/connectors.py — MCP 连接器 API

对接 agent_core.mcp_connector（ECO_MCP_SERVERS 配置驱动）与 tools_registry 的
全局 MCP 管理器（_MCP_MGR），提供连接器清单与连接状态：
  - GET  /connectors           列出连接器（名称/传输/URL/连接状态/工具数）
  - POST /connectors/refresh   重连全部 MCP（等价 system/reload 的 MCP 段）
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

logger = logging.getLogger("eco.server.connectors")

router = APIRouter()


def _rows() -> list[dict]:
    """配置清单 × 运行时连接状态（_MCP_MGR 未连接时仅回配置元信息）。"""
    import agent_core.tools_registry as tr
    from agent_core.mcp_connector import load_configs_from_env

    configs = load_configs_from_env()
    mgr = tr._MCP_MGR  # noqa: SLF001
    rows: list[dict] = []
    for cfg in configs:
        row: dict = {
            "name": cfg.name,
            "transport": cfg.transport,
            "url": cfg.url or "",
            "has_headers": bool(cfg.headers),
            "timeout": cfg.timeout,
            "connected": False,
            "last_error": "",
            "tool_count": 0,
            "tools": [],
        }
        if mgr is not None:
            conn = mgr.get(cfg.name)
            if conn is not None:
                row["connected"] = bool(conn.connected)
                row["last_error"] = conn.last_error or ""
                row["tool_count"] = len(conn.tools)
                row["tools"] = [t.get("name", "") for t in conn.tools]
        rows.append(row)
    return rows


@router.get("/connectors")
async def list_connectors() -> dict:
    rows = _rows()
    connected = sum(1 for r in rows if r["connected"])
    tool_total = sum(r["tool_count"] for r in rows)
    return {"count": len(rows), "connected": connected, "tool_total": tool_total, "connectors": rows}


@router.post("/connectors/refresh")
async def refresh_connectors() -> dict:
    import agent_core.tools_registry as tr

    # 先关闭旧连接再重建（避免 stdio 子进程泄漏，重连失败 → 0 工具）
    if tr._MCP_MGR is not None:  # noqa: SLF001
        try:
            tr._MCP_MGR.close()  # noqa: SLF001
        except Exception:  # noqa: BLE001
            pass
    tr._MCP_ATTACHED = False
    tr._MCP_MGR = None
    names = tr.attach_mcp_tools()
    rows = _rows()
    # mcp_count 取工具体系里实际注册的 mcp__ 处理器数（attach 返回偶有竞态，以 _HANDLERS 为准）
    mcp_count = len([n for n in tr._HANDLERS if n.startswith("mcp__")])
    return {
        "ok": True,
        "mcp_count": mcp_count or len(names),
        "connected": sum(1 for r in rows if r["connected"]),
        "tool_total": sum(r["tool_count"] for r in rows),
        "connectors": rows,
    }
