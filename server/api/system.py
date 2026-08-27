#!/usr/bin/env python3
"""
server/api/system.py — 系统健康与指标 API

聚合：版本、LLM 统计、调度任务、审计摘要、SOUL 状态。
"""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter
from pydantic import BaseModel, Field

from server.app import get_version

logger = logging.getLogger("eco.server.system")

router = APIRouter()


class PermissionGateBody(BaseModel):
    enabled: bool = Field(..., description="是否启用 L1-L4 权限闸门")


@router.get("/version")
async def version() -> dict:
    return {"version": get_version()}


@router.post("/system/permission-gate")
async def set_permission_gate(body: PermissionGateBody) -> dict:
    """运行时切换权限闸门（对标 DSH 权限预设）。改的是进程内环境变量，
    重启后回落到 .env 配置值；决策写 SM3 审计链（source=permission）。"""
    os.environ["ECO_PERMISSION_GATE"] = "1" if body.enabled else "0"
    try:
        from agent_core.prompt_engine import PromptAuditChain

        PromptAuditChain().append(
            source="permission",
            content=f"permission gate set to {'on' if body.enabled else 'off'} via system API",
            accepted=True, reason="gate_toggle_api")
    except Exception:  # noqa: BLE001 — 审计失败不影响切换
        logger.warning("permission gate 审计写入失败")
    return {"enabled": body.enabled,
            "note": "已切换；重启服务后回到 .env 配置值"}


@router.get("/system/presets")
async def list_presets() -> dict:
    """Agent 预设清单（对标 DSH ui-agent-preset 目录）：主 profile + 角色人格。"""
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent.parent / "profiles"
    presets = []
    main_dir = root / "eco-agent"
    if main_dir.is_dir():
        presets.append({"id": "eco-agent", "role": "main",
                        "name": "eco Agent（主预设）",
                        "files": sorted(p.name for p in main_dir.glob("*.md")) + ["config.yaml"]})
    agents_dir = root / "agents"
    if agents_dir.is_dir():
        for p in sorted(agents_dir.glob("*")):
            presets.append({"id": p.stem, "role": "agent",
                            "name": p.stem.replace("_soul", " 人格"),
                            "files": [p.name]})
    return {"presets": presets, "count": len(presets)}


@router.get("/system")
async def system_status() -> dict:
    out: dict = {"version": get_version(), "components": {}}

    # LLM
    try:
        from agent_core.llm_client import get_default_client

        client = get_default_client()
        out["components"]["llm"] = {
            "available": client.available(),
<<<<<<< HEAD
            # 注意：provider 名称在 client._provider_name（_provider 为 dict，无 "name" 键）
            "provider": getattr(client, "_provider_name", "unknown"),
=======
            "provider": getattr(client, "_provider", {}).get("name", "unknown"),
>>>>>>> a3797b5 (Add 10 Anthropic Skills + zhihu-fetch-skill)
            "stats": client.get_stats() if hasattr(client, "get_stats") else {},
        }
    except Exception as e:  # noqa: BLE001
        out["components"]["llm"] = {"available": False, "error": str(e)}

    # SOUL / prompt engine
    try:
        from agent_core.prompt_engine import get_prompt_engine

        eng = get_prompt_engine()
        out["components"]["soul"] = {"loaded": bool(getattr(eng.soul, "loaded", False))}
    except Exception as e:  # noqa: BLE001
        out["components"]["soul"] = {"loaded": False, "error": str(e)}

    # 调度器
    try:
        from agent_core.scheduler import CronScheduler

        sch = CronScheduler()
        out["components"]["scheduler"] = {
            "running": sch._running,  # noqa: SLF001
            "job_count": len(sch._jobs),  # noqa: SLF001
        }
    except Exception as e:  # noqa: BLE001
        out["components"]["scheduler"] = {"error": str(e)}

    # 记忆树
    try:
        from _scripts.memory_tree import MemoryTree

        tree = MemoryTree()
        out["components"]["memory"] = tree.get_stats()
    except Exception as e:  # noqa: BLE001
        out["components"]["memory"] = {"error": str(e)}

    # 权限闸门
    out["components"]["permission_gate"] = {
        "enabled": os.environ.get("ECO_PERMISSION_GATE", "1").strip().lower() not in ("0", "false", "no"),
    }

    return out


@router.get("/metrics")
async def metrics() -> dict:
    out: dict = {}
    try:
        from agent_core.llm_client import summarize_llm_stats

        stats = summarize_llm_stats()
        out["llm"] = {
            "calls": stats.get("calls", 0),
            "errors": stats.get("errors", 0),
            "prompt_tokens": stats.get("prompt_tokens", 0),
            "completion_tokens": stats.get("completion_tokens", 0),
            "total_elapsed_s": round(stats.get("total_elapsed_s", 0.0), 4),
        }
    except Exception as e:  # noqa: BLE001
        out["llm"] = {"error": str(e)}
    try:
        from agent_core.scheduler import CronScheduler

        sch = CronScheduler()
        out["scheduler"] = {"jobs": len(sch._jobs)}  # noqa: SLF001
    except Exception:  # noqa: BLE001
        out["scheduler"] = {"jobs": 0}
    return out

@router.get("/system/cordis")
async def cordis_snapshot() -> dict:
    """组合内核诊断：服务/插件/事件目录（对标 DSH Inspect list）。"""
    try:
        from agent_core.cordis.boot import get_app_context

        return get_app_context().snapshot()
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}



@router.post("/system/reload")
async def reload_system() -> dict:
    """热重载：重新加载 .env 环境变量 + 重连全部 MCP 服务器（不改代码、不重启进程）。

    挂载自闭环关键一环：改 .env（如新增 MCP server 条目）后调本端点即生效，
    无需人工重启服务器进程。"""
    import logging

    logger = logging.getLogger("eco.api.system")
    result: dict = {"env_reloaded": False, "mcp": []}
    try:
        from agent_core.envboot import load_env_into_process
        load_env_into_process()
        result["env_reloaded"] = True
    except Exception as e:  # noqa: BLE001
        result["env_error"] = str(e)
    try:
        import agent_core.tools_registry as tr

        # 先关闭旧连接再重建（否则 stdio 子进程泄漏，重连失败 → mcp=0）
        if tr._MCP_MGR is not None:
            try:
                tr._MCP_MGR.close()
            except Exception:
                pass
        tr._MCP_ATTACHED = False  # 强制下次 attach 全量重连
        tr._MCP_MGR = None
        names = tr.attach_mcp_tools()
        result["mcp"] = names[:10]
        result["mcp_count"] = len(names)
    except Exception as e:  # noqa: BLE001
        result["mcp_error"] = str(e)
    logger.info("[system/reload] env=%s mcp=%s", result["env_reloaded"], result.get("mcp_count"))
    return {"ok": True, **result}
