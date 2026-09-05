#!/usr/bin/env python3
"""
eco_agent_sdk/types.py — SDK 类型契约（与 server/api 端面一一对应）
"""

from __future__ import annotations

from typing import Any


class ChatRequest:
    """对话请求。"""

    def __init__(
        self,
        message: str,
        history: list[dict] | None = None,
        model: str = "",
        temperature: float = 0.7,
    ) -> None:
        self.message = message
        self.history = history or []
        self.model = model
        self.temperature = temperature

    def to_dict(self) -> dict:
        return {
            "message": self.message,
            "history": self.history,
            "model": self.model,
            "temperature": self.temperature,
        }


class ChatResponse:
    """对话响应。"""

    def __init__(self, reply: str, model: str = "", usage: dict | None = None) -> None:
        self.reply = reply
        self.model = model
        self.usage = usage or {}

    @classmethod
    def from_dict(cls, data: dict) -> ChatResponse:
        return cls(reply=str(data.get("reply", "")), model=str(data.get("model", "")), usage=dict(data.get("usage") or {}))


class VersionInfo:
    def __init__(self, version: str) -> None:
        self.version = version

    @classmethod
    def from_dict(cls, data: dict) -> VersionInfo:
        return cls(version=str(data.get("version", "")))


class SessionInfo:
    def __init__(
        self,
        session_id: str,
        platform: str = "",
        user_id: str = "",
        created_at: str = "",
        updated_at: str = "",
        message_count: int = 0,
    ) -> None:
        self.session_id = session_id
        self.platform = platform
        self.user_id = user_id
        self.created_at = created_at
        self.updated_at = updated_at
        self.message_count = message_count

    @classmethod
    def from_dict(cls, data: dict) -> SessionInfo:
        return cls(
            session_id=str(data.get("session_id", "")),
            platform=str(data.get("platform", "")),
            user_id=str(data.get("user_id", "")),
            created_at=str(data.get("created_at", "")),
            updated_at=str(data.get("updated_at", "")),
            message_count=int(data.get("message_count", 0)),
        )


class MemoryNode:
    def __init__(self, data: dict) -> None:
        self.id: str = str(data.get("id", ""))
        self.type: str = str(data.get("type", ""))
        self.title: str = str(data.get("title", ""))
        self.score: float = float(data.get("score", 0))
        self.updated_at: str = str(data.get("updated_at", ""))
        self.raw: dict = data

    @classmethod
    def from_dict(cls, data: dict) -> MemoryNode:
        return cls(data)


class MemoryStats:
    def __init__(self, total_nodes: int = 0, total_edges: int = 0, by_type: dict | None = None) -> None:
        self.total_nodes = total_nodes
        self.total_edges = total_edges
        self.by_type = by_type or {}

    @classmethod
    def from_dict(cls, data: dict) -> MemoryStats:
        return cls(
            total_nodes=int(data.get("total_nodes", 0)),
            total_edges=int(data.get("total_edges", 0)),
            by_type=dict(data.get("by_type") or {}),
        )


class SkillInfo:
    def __init__(self, name: str, data: dict | None = None) -> None:
        self.name = name
        self.raw = data or {}

    @property
    def manifest(self) -> dict:
        return self.raw.get("manifest", {}) if isinstance(self.raw.get("manifest"), dict) else {}

    @property
    def description(self) -> str:
        return str(self.manifest.get("description", ""))

    @property
    def tags(self) -> list:
        return list(self.manifest.get("tags", []))

    @property
    def version(self) -> str:
        return str(self.manifest.get("version", ""))

    @classmethod
    def from_dict(cls, data: dict) -> SkillInfo:
        return cls(name=str(data.get("name", "")), data=data)


class ToolEntry:
    def __init__(self, data: dict) -> None:
        self.name: str = str(data.get("name", ""))
        self.source: str = str(data.get("source", ""))
        self.description: str = str(data.get("description", ""))
        self.category: str = str(data.get("category", ""))
        self.tags: list = list(data.get("tags", []))
        self.approval_required: bool = bool(data.get("approval_required", False))

    @classmethod
    def from_dict(cls, data: dict) -> ToolEntry:
        return cls(data)


class SystemStatus:
    def __init__(self, data: dict) -> None:
        self.version: str = str(data.get("version", ""))
        self.components: dict[str, Any] = dict(data.get("components") or {})
        self.raw: dict = data

    def component(self, name: str) -> dict:
        c = self.components.get(name)
        return c if isinstance(c, dict) else {}

    @classmethod
    def from_dict(cls, data: dict) -> SystemStatus:
        return cls(data)
