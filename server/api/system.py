#!/usr/bin/env python3
"""
server/api/system.py — 系统健康与指标 API

聚合：版本、LLM 统计、调度任务、审计摘要、SOUL 状态。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from server.app import get_version

logger = logging.getLogger("eco.server.system")

router = APIRouter()


@router.get("/version")
async def version() -> dict:
    return {"version": get_version()}


@router.get("/system")
async def system_status() -> dict:
    out: dict = {"version": get_version(), "components": {}}

    # LLM
    try:
        from agent_core.llm_client import get_default_client

        client = get_default_client()
        out["components"]["llm"] = {
            "available": client.available(),
            "provider": getattr(client, "_provider", {}).get("name", "unknown"),
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
