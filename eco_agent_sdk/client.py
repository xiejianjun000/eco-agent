#!/usr/bin/env python3
"""
eco_agent_sdk/client.py — EcoClient（异步）+ SyncEcoClient（同步包装）

对接 eco-server 管理 API。端面契约见 server/api/* 模块文档。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from eco_agent_sdk.errors import EcoApiError, EcoConnectionError
from eco_agent_sdk.types import (
    ChatRequest,
    ChatResponse,
    MemoryNode,
    MemoryStats,
    SessionInfo,
    SkillInfo,
    SystemStatus,
    ToolEntry,
    VersionInfo,
)


class EcoClient:
    """异步客户端。默认连接本地 eco-server（127.0.0.1:8788）。"""

    def __init__(
        self, base_url: str = "http://127.0.0.1:8788", timeout: float = 60.0, client: httpx.AsyncClient | None = None
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = client or httpx.AsyncClient(base_url=self.base_url, timeout=timeout)
        self._owns_client = client is None

    async def __aenter__(self) -> EcoClient:
        return self

    async def __aexit__(self, *exc) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    # ── 底层 ──────────────────────────────────────────────

    async def _get(self, path: str, **params) -> dict:
        try:
            res = await self._client.get(path, params=params or None)
        except httpx.HTTPError as e:
            raise EcoConnectionError(f"无法连接 eco-server {self.base_url}: {e}") from e
        if res.status_code >= 400:
            raise EcoApiError(res.status_code, res.text[:300])
        return res.json()

    async def _post(self, path: str, body: dict) -> dict:
        try:
            res = await self._client.post(path, json=body)
        except httpx.HTTPError as e:
            raise EcoConnectionError(f"无法连接 eco-server {self.base_url}: {e}") from e
        if res.status_code >= 400:
            raise EcoApiError(res.status_code, res.text[:300])
        return res.json()

    # ── 基础 ──────────────────────────────────────────────

    async def health(self) -> dict:
        try:
            res = await self._client.get("/healthz")
        except httpx.HTTPError as e:
            raise EcoConnectionError(f"无法连接 eco-server {self.base_url}: {e}") from e
        if res.status_code >= 400:
            raise EcoApiError(res.status_code, res.text[:300])
        return res.json()

    async def version(self) -> VersionInfo:
        return VersionInfo.from_dict(await self._get("/api/v1/version"))

    # ── 对话 ──────────────────────────────────────────────

    async def chat(
        self, message: str, history: list[dict] | None = None, model: str = "", temperature: float = 0.7
    ) -> ChatResponse:
        req = ChatRequest(message=message, history=history, model=model, temperature=temperature)
        return ChatResponse.from_dict(await self._post("/api/v1/chat", req.to_dict()))

    async def chat_stream(
        self, message: str, history: list[dict] | None = None, model: str = "", temperature: float = 0.7
    ) -> AsyncIterator[str]:
        """SSE 流式对话，逐块 yield 文本增量。"""
        req = ChatRequest(message=message, history=history, model=model, temperature=temperature)
        try:
            async with self._client.stream("POST", "/api/v1/chat/stream", json=req.to_dict()) as res:
                if res.status_code >= 400:
                    body = await res.aread()
                    raise EcoApiError(res.status_code, body.decode(errors="replace")[:300])
                async for line in res.aiter_lines():
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        return
                    try:
                        obj = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    if obj.get("error"):
                        raise EcoApiError(0, str(obj["error"]))
                    if obj.get("delta"):
                        yield str(obj["delta"])
        except httpx.HTTPError as e:
            raise EcoConnectionError(f"流式连接失败: {e}") from e

    # ── 会话 ──────────────────────────────────────────────

    async def list_sessions(self) -> list[SessionInfo]:
        return [SessionInfo.from_dict(s) for s in await self._get("/api/v1/sessions")]

    async def create_session(self, user_id: str = "", user_name: str = "") -> SessionInfo:
        return SessionInfo.from_dict(await self._post("/api/v1/sessions", {"user_id": user_id, "user_name": user_name}))

    async def get_session(self, session_id: str) -> SessionInfo:
        return SessionInfo.from_dict(await self._get(f"/api/v1/sessions/{session_id}"))

    # ── 记忆 ──────────────────────────────────────────────

    async def memory_nodes(self, limit: int = 50, offset: int = 0, node_type: str | None = None) -> list[MemoryNode]:
        params = {"limit": limit, "offset": offset}
        if node_type:
            params["type"] = node_type
        return [MemoryNode.from_dict(n) for n in (await self._get("/api/v1/memory/nodes", **params))["nodes"]]

    async def memory_hot(self, limit: int = 20) -> list[MemoryNode]:
        return [MemoryNode.from_dict(n) for n in (await self._get("/api/v1/memory/hot", limit=limit))["nodes"]]

    async def memory_search(
        self, query: str, node_type: str | None = None, hybrid: bool = False, limit: int = 20
    ) -> list[MemoryNode]:
        params = {"q": query, "limit": limit}
        if node_type:
            params["type"] = node_type
        if hybrid:
            params["hybrid"] = "true"
        return [MemoryNode.from_dict(n) for n in (await self._get("/api/v1/memory/search", **params))["nodes"]]

    async def memory_stats(self) -> MemoryStats:
        return MemoryStats.from_dict(await self._get("/api/v1/memory/stats"))

    # ── 技能 ──────────────────────────────────────────────

    async def list_skills(self) -> list[SkillInfo]:
        return [SkillInfo.from_dict(s) for s in (await self._get("/api/v1/skills"))["skills"]]

    async def search_skills(self, keyword: str) -> list[SkillInfo]:
        return [SkillInfo.from_dict(s) for s in (await self._get("/api/v1/skills/search", q=keyword))["skills"]]

    async def get_skill(self, name: str) -> SkillInfo:
        return SkillInfo.from_dict(await self._get(f"/api/v1/skills/{name}"))

    # ── 工具 / 系统 ────────────────────────────────────────

    async def list_tools(self, source: str | None = None, q: str | None = None) -> list[ToolEntry]:
        params: dict = {}
        if source:
            params["source"] = source
        if q:
            params["q"] = q
        return [ToolEntry.from_dict(t) for t in (await self._get("/api/v1/tools", **params))["tools"]]

    async def tool_stats(self) -> dict:
        return await self._get("/api/v1/tools/stats")

    async def system(self) -> SystemStatus:
        return SystemStatus.from_dict(await self._get("/api/v1/system"))

    async def metrics(self) -> dict:
        return await self._get("/api/v1/metrics")


class SyncEcoClient:
    """同步客户端——内部以独立事件循环驱动 EcoClient。适合脚本/REPL 场景。"""

    def __init__(self, base_url: str = "http://127.0.0.1:8788", timeout: float = 60.0) -> None:
        import asyncio
        import threading

        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._client: EcoClient | None = None
        self._base_url = base_url
        self._timeout = timeout

    def _ensure(self) -> EcoClient:
        # loop 线程与 client 独立创建：允许测试注入 mock client 后复用同一驱动 loop
        if self._loop is None:
            import asyncio
            import threading

            self._loop = asyncio.new_event_loop()
            self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
            self._thread.start()
        if self._client is None:
            self._client = EcoClient(self._base_url, self._timeout)
        return self._client

    def _run(self, coro):
        import asyncio

        self._ensure()
        assert self._loop is not None
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result()

    def __getattr__(self, name: str):
        """把同步调用委托给 EcoClient 的异步方法（不含 chat_stream 等异步迭代器）。"""
        client = self._ensure()
        method = getattr(client, name)

        def wrapper(*args, **kwargs):
            result = self._run(method(*args, **kwargs))
            if hasattr(result, "__aiter__"):
                raise TypeError(f"{name} 是异步迭代器方法，请使用 EcoClient（异步）")

            return result

        return wrapper

    def close(self) -> None:
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._loop = None
            self._thread = None
            self._client = None
