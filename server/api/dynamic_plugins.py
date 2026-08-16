"""
server/api/dynamic_plugins.py — 动态插件 REST 接口（对标 DSH tool-cordis）

POST /api/v1/dynplugins/define  {code, name?} → {plugin_id, precheck}
GET  /api/v1/dynplugins         列表 + 状态
GET  /api/v1/dynplugins/{id}    源码（inspect self）
POST /api/v1/dynplugins/{id}/run   {config?} → 激活（需 ECO_DYNAMIC_PLUGINS=1）
POST /api/v1/dynplugins/{id}/stop
DELETE /api/v1/dynplugins/{id}    undefine（先 stop）
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agent_core.dynamic_plugin import get_dynamic_plugin_registry

logger = logging.getLogger("eco.api.dynplugins")
router = APIRouter()


class DefineRequest(BaseModel):
    code: str = Field(..., description="插件代码（inject 列表 + apply(ctx, config)）")
    name: str = Field(default="", description="插件名（注释用）")
    plugin_id: str | None = Field(default=None, description="覆盖更新指定插件")


class RunRequest(BaseModel):
    config: dict = Field(default_factory=dict, description="插件配置")


@router.post("/dynplugins/define")
async def define_plugin(req: DefineRequest) -> dict:
    reg = get_dynamic_plugin_registry()
    out = reg.define(req.code, name=req.name, plugin_id=req.plugin_id)
    if not out.get("ok"):
        raise HTTPException(status_code=400, detail=out.get("precheck", {}).get("error"))
    return out


@router.get("/dynplugins")
async def list_plugins() -> dict:
    reg = get_dynamic_plugin_registry()
    return {"plugins": reg.list(), "stats": reg.stats()}


@router.get("/dynplugins/{plugin_id}")
async def get_plugin_source(plugin_id: str) -> dict:
    reg = get_dynamic_plugin_registry()
    out = reg.get_source(plugin_id)
    if not out.get("ok"):
        raise HTTPException(status_code=404, detail=out.get("error"))
    return out


@router.post("/dynplugins/{plugin_id}/run")
async def run_plugin(plugin_id: str, req: RunRequest) -> dict:
    reg = get_dynamic_plugin_registry()
    out = reg.run(plugin_id, config=req.config)
    if not out.get("ok"):
        raise HTTPException(status_code=409, detail=out.get("error", ""))
    return out


@router.post("/dynplugins/{plugin_id}/stop")
async def stop_plugin(plugin_id: str) -> dict:
    reg = get_dynamic_plugin_registry()
    out = reg.stop(plugin_id)
    if not out.get("ok"):
        raise HTTPException(status_code=404, detail=out.get("error", ""))
    return out


@router.delete("/dynplugins/{plugin_id}")
async def undefine_plugin(plugin_id: str) -> dict:
    reg = get_dynamic_plugin_registry()
    return reg.undefine(plugin_id)
