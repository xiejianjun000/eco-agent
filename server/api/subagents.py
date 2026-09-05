"""
server/api/subagents.py — 子代理 REST 接口（对标 DSH subagent 工具）

POST   /api/v1/subagents             发起子代理 {message, history?, model?, background?}
GET    /api/v1/subagents             目录列表（含状态）
GET    /api/v1/subagents/{id}        详情 + 增量输出（?since_seq=N）
POST   /api/v1/subagents/{id}/message  续聊（send_message）
POST   /api/v1/subagents/{id}/interrupt 中断运行中的子代理
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agent_core.subagent import get_subagent_registry

logger = logging.getLogger("eco.api.subagents")
router = APIRouter()


class SubagentSpawnRequest(BaseModel):
    message: str = Field(..., description="子代理任务提示词")
    history: list[dict] = Field(default_factory=list, description="父会话历史前缀（fork）")
    model: str = Field(default="", description="模型名，留空用默认")
    background: bool = Field(default=True, description="后台运行（False 时同步等待结果）")
    label: str = Field(default="", description="显示标签")
    parent_id: str | None = Field(default=None, description="父会话 id（审计用）")


class SubagentMessageRequest(BaseModel):
    message: str = Field(..., description="追加给子代理的消息")


@router.post("")
async def spawn_subagent(req: SubagentSpawnRequest) -> dict:
    reg = get_subagent_registry()
    snap = reg.start(
        req.message, history=req.history, model=req.model, background=req.background, label=req.label, parent_id=req.parent_id
    )
    if not req.background:
        # 前台：等结果（同步语义，供脚本/测试用）
        agent = reg.get(snap["id"])
        if agent is not None and agent._task is not None:
            await agent._task
        final = reg.get(snap["id"])
        out = final.snapshot() if final else snap
        out.update({"result": final.result if final else None})
        return out
    return snap


@router.get("")
async def list_subagents() -> dict:
    reg = get_subagent_registry()
    return {"agents": reg.list(), "stats": reg.stats()}


@router.get("/{agent_id}")
async def get_subagent(agent_id: str, since_seq: int = 0) -> dict:
    reg = get_subagent_registry()
    agent = reg.get(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"子代理不存在: {agent_id}")
    output, current_seq = agent.read_output(since_seq)
    return {"agent": agent.snapshot(), "output": output, "seq": current_seq}


@router.post("/{agent_id}/message")
async def send_message(agent_id: str, req: SubagentMessageRequest) -> dict:
    reg = get_subagent_registry()
    try:
        return reg.send_message(agent_id, req.message)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"子代理不存在: {agent_id}") from None
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from None


@router.post("/{agent_id}/interrupt")
async def interrupt_subagent(agent_id: str) -> dict:
    reg = get_subagent_registry()
    ok = reg.interrupt(agent_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"子代理不存在或已结束: {agent_id}")
    return {"id": agent_id, "interrupted": True}
