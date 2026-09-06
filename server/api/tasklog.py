#!/usr/bin/env python3
"""
server/api/tasklog.py — 任务日志 API（WorkBuddy memory 面板对标）

GET /api/v1/task-log?days=7 → 近 N 天任务段记忆（按天工作日志）原文 + 统计。
供前端右栏「日志」视图渲染（WorkBuddy .workbuddy/memory 可视化）。
"""

from __future__ import annotations

from fastapi import APIRouter, Query

router = APIRouter()


@router.get("/task-log")
async def get_task_log(days: int = Query(default=7, ge=1, le=30)) -> dict:
    from agent_core.task_log import load_recent_task_logs, stats

    return {
        "stats": stats(),
        "days": days,
        "content": load_recent_task_logs(days=days, max_chars=10000),
    }
