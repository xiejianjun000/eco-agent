#!/usr/bin/env python3
"""
server/api/sessions.py — 会话 API

复用 gateway_core.SessionManager（platform="web"），跨通道统一会话。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger("eco.server.sessions")

router = APIRouter()


class SessionCreate(BaseModel):
    user_id: str = Field(default="", description="用户标识，留空自动生成")
    user_name: str = Field(default="", description="用户名称")


class SessionOut(BaseModel):
    session_id: str
    platform: str
    user_id: str
    created_at: str
    updated_at: str
    message_count: int = 0


def _session_mgr():
    from gateway.gateway_core import SessionManager

    return SessionManager()


@router.get("/sessions")
async def list_sessions() -> list[SessionOut]:
    mgr = _session_mgr()
    sessions = list(mgr._sessions.values())  # noqa: SLF001 — 只读快照
    out = []
    for s in sessions:
        if s.platform != "web":
            continue
        out.append(SessionOut(
            session_id=s.session_id,
            platform=s.platform,
            user_id=s.user_id,
            created_at=s.created_at,
            updated_at=s.updated_at,
            message_count=len(getattr(s, "messages", [])),
        ))
    return out


@router.post("/sessions")
async def create_session(body: SessionCreate) -> SessionOut:
    import uuid

    mgr = _session_mgr()
    uid = body.user_id or f"web-{uuid.uuid4().hex[:8]}"
    s = mgr.get_or_create("web", channel_id=uid, user_id=uid, user_name=body.user_name)
    return SessionOut(
        session_id=s.session_id, platform=s.platform, user_id=s.user_id,
        created_at=s.created_at, updated_at=s.updated_at,
        message_count=len(getattr(s, "messages", [])),
    )


@router.get("/sessions/{session_id}")
async def get_session(session_id: str) -> SessionOut:
    mgr = _session_mgr()
    s = mgr.get(session_id)
    if s is None:
        raise HTTPException(status_code=404, detail="session not found")
    return SessionOut(
        session_id=s.session_id, platform=s.platform, user_id=s.user_id,
        created_at=s.created_at, updated_at=s.updated_at,
        message_count=len(getattr(s, "messages", [])),
    )


@router.get("/sessions/{session_id}/messages")
async def get_session_messages(session_id: str) -> dict:
    """从 session_log（SHA-256 链）重放对话消息，供前端重启后恢复。"""
    from agent_core.session_log import SessionEventLog

    slog = SessionEventLog(f"web/{session_id}")
    messages: list[dict] = []
    for e in slog.replay():
        if e.get("type") == "user/message":
            messages.append({"role": "user", "content": e["data"].get("content", "")})
        elif e.get("type") == "assistant/message":
            messages.append({"role": "assistant", "content": e["data"].get("content", "")})
    return {"session_id": session_id, "messages": messages,
            "count": len(messages)}
