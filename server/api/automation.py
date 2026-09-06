#!/usr/bin/env python3
"""
server/api/automation.py — 自动任务（Cron 定时调度）API

对接 agent_core.scheduler 全局单例（cron_scheduler 插件已通电），提供：
  - GET  /automation/jobs            列出定时任务 + 运行状态
  - POST /automation/jobs            新建（自然语言或显式 cron）
  - DELETE /automation/jobs/{id}     删除
  - POST /automation/jobs/{id}/run   手动触发一次
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel, Field

logger = logging.getLogger("eco.server.automation")

router = APIRouter()


class JobCreate(BaseModel):
    description: str | None = Field(
        default=None,
        description="自然语言描述（如：每天 9 点巡查娄底市空气质量）",
    )
    cron_expr: str | None = Field(default=None, description="显式 cron 表达式（与 task_desc 配合）")
    task_desc: str | None = Field(default=None, description="任务描述")


def _scheduler():
    """全局 CronScheduler 单例（cron_scheduler 插件启动的同一个实例）。"""
    from agent_core.scheduler import scheduler

    return scheduler


@router.get("/automation/jobs")
async def list_jobs() -> dict:
    sch = _scheduler()
    jobs = sch.list_jobs()
    return {
        "running": getattr(sch, "_running", False),
        "count": len(jobs),
        "jobs": jobs,
        "stats": sch.get_stats(),
    }


@router.post("/automation/jobs")
async def add_job(body: JobCreate) -> dict:
    sch = _scheduler()
    if body.cron_expr:
        desc = body.task_desc or body.description or "定时任务"
        job_id = sch.add_job(body.cron_expr, desc)
    elif body.description:
        job_id = sch.add_from_nl(body.description.strip())
    else:
        return {"ok": False, "error": "需提供 description（自然语言）或 cron_expr（显式表达式）"}
    if not job_id:
        return {"ok": False, "error": "无法把描述解析为 cron 表达式（支持：每天/每小时/每周/每月/每 N 分钟/秒）"}
    return {"ok": True, "job_id": job_id}


@router.delete("/automation/jobs/{job_id}")
async def remove_job(job_id: str) -> dict:
    sch = _scheduler()
    return {"ok": sch.remove_job(job_id)}


@router.post("/automation/jobs/{job_id}/run")
async def run_job(job_id: str) -> dict:
    sch = _scheduler()
    return sch.run_job(job_id)
