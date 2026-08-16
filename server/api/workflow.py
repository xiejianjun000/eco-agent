"""
server/api/workflow.py — Workflow 编排 REST 接口（对标 DSH workflow 工具）

POST /api/v1/workflow  {script, args?, timeout?} → {ok, result, log, duration_ms}
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel, Field

from agent_core.workflow import run_workflow

logger = logging.getLogger("eco.api.workflow")
router = APIRouter()


class WorkflowRequest(BaseModel):
    script: str = Field(..., description="编排脚本（同步 Python，hooks: agent/pipeline/parallel/phase/log/args）")
    args: dict = Field(default_factory=dict, description="脚本 args 全局 JSON 参数")
    timeout: int = Field(default=600, ge=10, le=1800, description="超时秒数")


@router.post("/workflow")
async def run_workflow_endpoint(req: WorkflowRequest) -> dict:
    return run_workflow(req.script, args=req.args, timeout=req.timeout)
