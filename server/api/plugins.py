#!/usr/bin/env python3
"""
server/api/plugins.py — 插件管理 API

复用 agent_core.plugins.PluginManager（扫描/热加载/卸载/重载/调用）。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger("eco.server.plugins")

router = APIRouter()


class ToolCallRequest(BaseModel):
    tool: str
    arguments: dict = {}


def _manager():
    from agent_core.plugins import get_plugin_manager

    return get_plugin_manager()


@router.get("/plugins")
async def list_plugins() -> dict:
    plugins = _manager().list()
    return {"count": len(plugins), "plugins": plugins}


@router.get("/plugins/{name}")
async def get_plugin(name: str) -> dict:
    info = _manager().get(name)
    if info is None:
        raise HTTPException(status_code=404, detail="plugin not found")
    return info


@router.post("/plugins/{name}/load")
async def load_plugin(name: str, force: bool = False) -> dict:
    result = _manager().load(name, force=force)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "load failed"))
    return result


@router.post("/plugins/{name}/unload")
async def unload_plugin(name: str) -> dict:
    result = _manager().unload(name)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "unload failed"))
    return result


@router.post("/plugins/{name}/reload")
async def reload_plugin(name: str) -> dict:
    result = _manager().reload(name)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "reload failed"))
    return result


@router.post("/plugins/call")
async def call_plugin_tool(body: ToolCallRequest) -> dict:
    try:
        result = _manager().call_tool(body.tool, body.arguments)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    return {"ok": True, "tool": body.tool, "result": result}
