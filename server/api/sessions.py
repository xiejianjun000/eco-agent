#!/usr/bin/env python3
"""
server/api/sessions.py — 会话 API

复用 gateway_core.SessionManager（platform="web"），跨通道统一会话。
扩展能力：重命名（PATCH）/ 删除（DELETE）/ 分享导出（GET .../export）。
显示名持久化在工作区 session_names.json（覆盖 default 等伪会话）。
"""

from __future__ import annotations

import json
import logging
import re
import threading
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger("eco.server.sessions")

router = APIRouter()

# session_id 白名单：防路径穿越（default / web_xxx / web-xxx 等）
_SID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")

_names_lock = threading.RLock()


class SessionCreate(BaseModel):
    user_id: str = Field(default="", description="用户标识，留空自动生成")
    user_name: str = Field(default="", description="用户名称")


class SessionRename(BaseModel):
    name: str = Field(default="", description="会话显示名，≤60 字")


class SessionOut(BaseModel):
    session_id: str
    platform: str
    user_id: str
    created_at: str
    updated_at: str
    message_count: int = 0
    name: str = ""


def _check_sid(session_id: str) -> None:
    if not _SID_RE.match(session_id or ""):
        raise HTTPException(status_code=400, detail="非法 session_id")


def _names_path() -> Path:
    from agent_core.workspace import WS_ROOT

    return WS_ROOT / "session_names.json"


def _load_names() -> dict[str, str]:
    try:
        data = json.loads(_names_path().read_text("utf-8", errors="replace"))
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _save_names(data: dict[str, str]) -> None:
    try:
        p = _names_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:  # noqa: BLE001 — 改名失败不阻断
        logger.warning("session_names.json 写入失败")


def _session_mgr():
    from gateway.gateway_core import SessionManager

    return SessionManager()


def _log_stats(session_id: str) -> tuple[int, str]:
    """从 session_log（SHA-256 链）取真实消息数与最近更新时间。

    聊天消息落盘在 SessionEventLog("web/{session_id}")，SessionManager 的
    messages 只覆盖 gateway 通道——Web 会话的真实计数/活跃时间以此为准。
    """
    try:
        from agent_core.session_log import SessionEventLog

        slog = SessionEventLog(f"web/{session_id}")
        count = 0
        last_time = 0.0
        for e in slog.replay():
            if e.get("type") in ("user/message", "assistant/message"):
                count += 1
            t = e.get("time") or 0
            if isinstance(t, (int, float)) and t > last_time:
                last_time = t
        if last_time <= 0:
            return count, ""
        return count, datetime.fromtimestamp(last_time).astimezone().isoformat()
    except Exception:  # noqa: BLE001 — 日志读取失败不阻断会话列表
        return 0, ""


def _to_out(s) -> SessionOut:
    log_count, log_updated = _log_stats(s.session_id)
    return SessionOut(
        session_id=s.session_id, platform=s.platform, user_id=s.user_id,
        created_at=s.created_at,
        updated_at=log_updated or s.updated_at,
        message_count=log_count or len(getattr(s, "messages", [])),
        name=_load_names().get(s.session_id, ""),
    )


@router.get("/sessions")
async def list_sessions() -> list[SessionOut]:
    mgr = _session_mgr()
    sessions = list(mgr._sessions.values())  # noqa: SLF001 — 只读快照
    out = [_to_out(s) for s in sessions if s.platform == "web"]
    # 「default」会话（Web 首页默认通道）若已有聊天记录，同样列入列表
    try:
        from agent_core.session_log import SessionEventLog

        slog = SessionEventLog("web/default")
        if slog.path.exists():
            count, updated = _log_stats("default")
            if count > 0:
                out.append(SessionOut(
                    session_id="default", platform="web", user_id="default",
                    created_at=updated, updated_at=updated, message_count=count,
                    name=_load_names().get("default", "")))
    except Exception:  # noqa: BLE001
        pass
    out.sort(key=lambda x: x.updated_at, reverse=True)
    return out


@router.post("/sessions")
async def create_session(body: SessionCreate) -> SessionOut:
    import uuid

    mgr = _session_mgr()
    uid = body.user_id or f"web-{uuid.uuid4().hex[:8]}"
    s = mgr.get_or_create("web", channel_id=uid, user_id=uid, user_name=body.user_name)
    return _to_out(s)


@router.get("/sessions/{session_id}")
async def get_session(session_id: str) -> SessionOut:
    _check_sid(session_id)
    mgr = _session_mgr()
    s = mgr.get(session_id)
    if s is None:
        raise HTTPException(status_code=404, detail="session not found")
    return _to_out(s)


@router.patch("/sessions/{session_id}")
async def rename_session(session_id: str, body: SessionRename) -> SessionOut:
    """重命名会话（显示名），持久化到工作区 session_names.json。"""
    _check_sid(session_id)
    name = (body.name or "").strip()[:60]
    with _names_lock:
        names = _load_names()
        names[session_id] = name
        _save_names(names)

    mgr = _session_mgr()
    s = mgr.get(session_id)
    if s is None:
        if session_id == "default":
            return SessionOut(session_id="default", platform="web", user_id="default",
                              created_at="", updated_at="", message_count=0, name=name)
        raise HTTPException(status_code=404, detail="session not found")
    return _to_out(s)


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str) -> dict:
    """删除会话：移除 SessionManager 条目 + 会话日志链 + 显示名。"""
    _check_sid(session_id)
    mgr = _session_mgr()
    removed = None
    with mgr._lock:  # noqa: SLF001
        removed = mgr._sessions.pop(session_id, None)
    if removed is not None:
        mgr._save()  # noqa: SLF001

    from agent_core.session_log import SessionEventLog

    slog = SessionEventLog(f"web/{session_id}")
    deleted_log = False
    with slog._lock:  # noqa: SLF001
        if slog.path.exists():
            slog.path.unlink()
            deleted_log = True

    with _names_lock:
        names = _load_names()
        if session_id in names:
            del names[session_id]
            _save_names(names)

    if removed is None and not deleted_log:
        raise HTTPException(status_code=404, detail="session not found")
    return {"ok": True, "session_id": session_id, "deleted_log": deleted_log}


@router.get("/sessions/{session_id}/export")
async def export_session(session_id: str) -> dict:
    """分享会话内容：重放日志链导出 Markdown，落盘 output/ 并返回全文供复制。"""
    _check_sid(session_id)
    from agent_core.session_log import SessionEventLog

    slog = SessionEventLog(f"web/{session_id}")
    msgs: list[tuple[str, str]] = []
    for e in slog.replay():
        if e.get("type") == "user/message":
            msgs.append(("我", e.get("data", {}).get("content", "")))
        elif e.get("type") == "assistant/message":
            msgs.append(("eco Agent", e.get("data", {}).get("content", "")))
    if not msgs:
        raise HTTPException(status_code=404, detail="会话没有可导出的内容")

    names = _load_names()
    title = names.get(session_id, "") or session_id
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = Path(__file__).resolve().parent.parent.parent / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"会话导出-{session_id[:24]}-{ts}.md"

    lines = [
        f"# eco Agent 会话导出：{title}",
        "",
        f"- 会话 ID: `{session_id}`",
        f"- 导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 消息数: {len(msgs)}",
        "",
    ]
    for role, content in msgs:
        lines.append(f"## {role}")
        lines.append("")
        lines.append(content)
        lines.append("")
    full = "\n".join(lines)
    path.write_text(full, encoding="utf-8")
    return {"ok": True, "path": str(path), "content": full, "count": len(msgs)}


@router.get("/sessions/{session_id}/messages")
async def get_session_messages(session_id: str) -> dict:
    """从 session_log（SHA-256 链）重放对话消息，供前端重启后恢复。"""
    _check_sid(session_id)
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
