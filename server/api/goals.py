"""
server/api/goals.py — 跨轮目标 REST 接口（对标 DSH tool-goal）

POST   /api/v1/goals           创建目标 {objective, max_goal_rounds?, auto_run?}
GET    /api/v1/goals           目标列表 + 统计
GET    /api/v1/goals/{id}      详情
POST   /api/v1/goals/{id}/{action}  操作: pause/resume/complete/block/run
"""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from agent_core.goal import get_goal_store

logger = logging.getLogger("eco.api.goals")
router = APIRouter()


class GoalCreate(BaseModel):
    objective: str = Field(..., description="目标描述")
    max_goal_rounds: int = Field(default=10, ge=1, le=256, description="自动延续轮次上限")
    auto_run: bool = Field(default=False, description="创建后立即发起首轮")
    context: str = Field(default="", description="初始上下文")


class GoalAction(BaseModel):
    note: str = Field(default="", description="操作备注（complete/block 用）")
    reason: str = Field(default="", description="阻塞原因（block 用）")


@router.post("/goals")
async def create_goal(body: GoalCreate) -> dict:
    store = get_goal_store()
    return store.create(body.objective, max_goal_rounds=body.max_goal_rounds,
                        auto_run=body.auto_run, context=body.context)


@router.get("/goals")
async def list_goals() -> dict:
    store = get_goal_store()
    return {"goals": store.list(), "stats": store.stats()}


@router.get("/goals/events")
async def goal_events(limit: int = Query(default=20, ge=1, le=200)) -> dict:
    """后台目标事件流（轮次完成/阻塞通知，Web 端轮询展示自动汇报）。"""
    import json as _json
    from pathlib import Path

    p = Path(os.environ.get("ECO_DIR") or Path.home() / ".eco") / "goal_notifications.jsonl"
    events: list[dict] = []
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines()[-limit:]:
            line = line.strip()
            if line:
                try:
                    events.append(_json.loads(line))
                except _json.JSONDecodeError:
                    pass
    return {"count": len(events), "events": events}


@router.get("/goals/{goal_id}")
async def get_goal(goal_id: str) -> dict:
    store = get_goal_store()
    goal = store.get(goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail=f"目标不存在: {goal_id}")
    return goal


@router.post("/goals/{goal_id}/{action}")
async def goal_action(goal_id: str, action: str, body: GoalAction) -> dict:
    store = get_goal_store()
    handlers = {
        "pause": lambda: store.pause(goal_id),
        "resume": lambda: store.resume(goal_id),
        "complete": lambda: store.complete(goal_id, body.note),
        "block": lambda: store.block(goal_id, body.reason or "manual"),
        "run": lambda: store.run_next_round(goal_id),
    }
    handler = handlers.get(action)
    if handler is None:
        raise HTTPException(status_code=400, detail=f"未知操作: {action}")
    result = handler()
    if result is None or (isinstance(result, dict) and not result.get("ok") and result.get("error")):
        if isinstance(result, dict) and result.get("error") and "不存在" not in result["error"]:
            raise HTTPException(status_code=409, detail=result["error"])
    return result or {}


