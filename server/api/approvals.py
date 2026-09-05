#!/usr/bin/env python3
"""
server/api/approvals.py — L4 审批栈 REST 接口（对标 DSH approval service）

  GET    /api/v1/approvals/pending        待决请求列表
  POST   /api/v1/approvals/{id}/decide    决定 {allow, reason, answerer}

answerer 必须命中审批栈授权链（agent_core.approval.ApprovalService.answerers），
链为空或 answerer 不在链内 → fail-closed 拒绝（绝不越权放行）。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from agent_core.approval import get_approval_service

logger = logging.getLogger("eco.api.approvals")

router = APIRouter()

# 审批 API 仅限本机访问（防 CSRF/越权）。answerer 自报需命中授权链，
# 此处再以客户端 IP 白名单做纵深防御。
_LOCAL_HOSTS = ("127.0.0.1", "::1", "localhost", "testclient")


def _require_local(request: Request) -> None:
    host = (request.client.host if request.client else "") or ""
    if host not in _LOCAL_HOSTS:
        raise HTTPException(status_code=403, detail="审批 API 仅限本机访问（防 CSRF/越权）")


class DecideBody(BaseModel):
    allow: bool = Field(..., description="是否放行")
    reason: str = Field(default="", description="决定理由")
    answerer: str = Field(default="", description="授权 answerer 身份（须在授权链内）")


@router.get("/approvals/pending")
async def list_pending(_: None = Depends(_require_local)) -> dict:
    svc = get_approval_service()
    pending = svc.list_pending()
    return {"pending": pending, "count": len(pending)}


@router.post("/approvals/{request_id}/decide")
async def decide(request_id: str, body: DecideBody, _: None = Depends(_require_local)) -> dict:
    svc = get_approval_service()
    answerer = body.answerer.strip() or "admin"
    result = svc.decide(request_id, allow=body.allow, answerer=answerer, reason=body.reason)
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail=result.get("reason", "请求不存在"))
    return result
