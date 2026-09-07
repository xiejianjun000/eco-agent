"""
server/api/slots.py — Slot 面板 API（对标 DSH Slot 查询）

GET /api/v1/slots          面板清单（挂点/标题/描述）
GET /api/v1/slots/{id}/data 面板数据（插件 provider 输出）
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException

from agent_core.slots import get_slot_registry

logger = logging.getLogger("eco.api.slots")
router = APIRouter()


@router.get("/slots")
async def list_slots() -> dict:
    reg = get_slot_registry()
    return {"slots": reg.list(), "stats": reg.stats()}


@router.get("/slots/{panel_id}/data")
async def slot_data(panel_id: str) -> dict:
    # provider 可能是重同步计算（审计链首次 SM3 重算实测 ~25 秒），
    # 直接在事件循环里跑会卡死整个服务；放线程池执行。
    reg = get_slot_registry()
    data = await asyncio.to_thread(reg.get_data, panel_id)
    if "error" in data and data.get("error") == "面板不存在":
        raise HTTPException(status_code=404, detail=data["error"])
    return data
