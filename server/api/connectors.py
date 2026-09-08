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
    """配置清单 × 运行时连接状态。"""
    import agent_core.tools_registry as tr
    from agent_core.mcp_connector import load_configs_from_env

    configs = load_configs_from_env()
    # 先确保挂载已发生，否则这个端点会在 MCP 尚未挂载时把 14 台全报
    # connected=False / tool_count=0 —— 而它们其实连得好好的。
    # 这正是自检端点最不该犯的错：用「还没连」冒充「连不上」。
    # attach_mcp_tools() 幂等，已挂载时直接返回。
    if tr._MCP_MGR is None:  # noqa: SLF001
        try:
            tr.attach_mcp_tools()
        except Exception:  # noqa: BLE001
            pass  # 连不上就如实回落到配置元信息
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
    # _rows() 是同步阻塞的，且可能触发 attach_mcp_tools()（冷启动数十秒）。
    # 直接在事件循环里跑会冻结整个 loop —— 包括正在用 api_probe 探测本端点的
    # 那次对话，于是自检工具把自己堵死，返回 timeout，
    # 模型据此得出「无法获取远程 MCP 连通状态」。
    # 丢线程池执行，让循环继续处理探测请求。
    import asyncio

    rows = await asyncio.get_running_loop().run_in_executor(None, _rows)
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


@router.post("/connectors/health")
async def health_check_connectors() -> dict:
    """轻量健康检查：只对掉线的 server 重连，不动正常连接。

    与 /connectors/refresh 的区别：refresh 是全量重建（close 掉所有连接再重连，
    正常的那些也会被断开重来，代价大）；本端点只修掉线的那几台。
    远程 MCP 会不定时掉线，这是巡检之外的手动补救入口。
    """
    import asyncio

    import agent_core.tools_registry as tr

    mgr = tr._MCP_MGR  # noqa: SLF001
    if mgr is None:
        return {"ok": False, "error": "MCP 尚未挂载", "checked": 0}
    # health_check 内部会对不可达主机做秒级超时连接，丢线程池避免阻塞事件循环
    status = await asyncio.get_running_loop().run_in_executor(None, mgr.health_check)
    rows = await asyncio.get_running_loop().run_in_executor(None, _rows)
    recovered = [n for n, ok in status.items() if ok]
    down = [n for n, ok in status.items() if not ok]
    return {
        "ok": True,
        "checked": len(status),
        "connected": sum(1 for r in rows if r["connected"]),
        "tool_total": sum(r["tool_count"] for r in rows),
        "down": down,
        "recovered_or_healthy": recovered,
    }
