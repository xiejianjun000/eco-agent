#!/usr/bin/env python3
"""
server/api/tasks.py — 持久化任务 API（WorkBuddy TaskCreate/Update/Get/List 对标）

GET  /api/v1/tasks?status= 列出任务
GET  /api/v1/tasks/{id}     单个任务详情
POST /api/v1/tasks          创建
PATCH /api/v1/tasks/{id}    更新（状态机在 task_store 层强制）
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class CreateBody(BaseModel):
    title: str
    description: str = ""
    priority: str = "normal"
    tags: list[str] | None = None


class UpdateBody(BaseModel):
    status: str | None = None
    title: str | None = None
    description: str | None = None
    priority: str | None = None
    tags: list[str] | None = None


@router.get("/tasks")
async def list_tasks(status: str | None = None, limit: int = 50) -> dict:
    from agent_core import task_store

    return task_store.list_tasks(status, limit)


@router.get("/tasks/{task_id}")
async def get_task(task_id: str) -> dict:
    from agent_core import task_store

    r = task_store.get_task(task_id)
    if not r.get("ok"):
        raise HTTPException(status_code=404, detail=r.get("error", "not found"))
    return r


@router.post("/tasks")
async def create_task(body: CreateBody) -> dict:
    from agent_core import task_store

    r = task_store.create_task(body.title, body.description, body.priority, body.tags)
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=r.get("error"))
    return r


@router.patch("/tasks/{task_id}")
async def update_task(task_id: str, body: UpdateBody) -> dict:
    from agent_core import task_store

    r = task_store.update_task(
        task_id, body.status, body.title, body.description, body.priority, body.tags
    )
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=r.get("error"))
    return r
