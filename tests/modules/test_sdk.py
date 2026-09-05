#!/usr/bin/env python3
"""
tests/modules/test_sdk.py — eco_agent_sdk 单元测试（httpx MockTransport）

覆盖：类型契约、API 错误、连接错误、chat/stream 解析、各资源端点。
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))


import httpx  # noqa: E402
import pytest  # noqa: E402

from eco_agent_sdk import (  # noqa: E402
    ChatResponse,
    EcoApiError,
    EcoClient,
    EcoConnectionError,
)


def _client(handler) -> EcoClient:
    transport = httpx.MockTransport(handler)
    return EcoClient(base_url="http://test", client=httpx.AsyncClient(transport=transport, base_url="http://test"))


def _json_handler(payload: dict):
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    return handler


def test_health():
    async def handler(request):
        return httpx.Response(200, json={"status": "ok", "version": "5.0.0a8"})

    client = _client(handler)

    async def run():
        data = await client.health()
        assert data["status"] == "ok"

    import asyncio

    asyncio.run(run())


def test_version():
    client = _client(_json_handler({"version": "5.0.0a8"}))

    async def run():
        v = await client.version()
        assert v.version == "5.0.0a8"

    import asyncio

    asyncio.run(run())


def test_chat_parse():
    client = _client(_json_handler({"reply": "你好", "model": "deepseek", "usage": {"total_tokens": 42}}))

    async def run():
        r = await client.chat("hi")
        assert isinstance(r, ChatResponse)
        assert r.reply == "你好"
        assert r.usage["total_tokens"] == 42

    import asyncio

    asyncio.run(run())


def test_chat_request_serialization():
    from eco_agent_sdk import ChatRequest

    req = ChatRequest("问题", history=[{"role": "user", "content": "前文"}], model="m", temperature=0.3)
    d = req.to_dict()
    assert d["message"] == "问题"
    assert d["history"][0]["role"] == "user"
    assert d["temperature"] == 0.3


def test_chat_stream():
    lines = [
        'data: {"delta": "你"}\n\n',
        'data: {"delta": "好"}\n\n',
        "data: [DONE]\n\n",
    ]

    async def handler(request: httpx.Request) -> httpx.Response:
        async def body():
            for line in lines:
                yield line.encode()

        return httpx.Response(200, content=body(), headers={"content-type": "text/event-stream"})

    client = _client(handler)

    async def run():
        chunks = []
        async for c in client.chat_stream("hi"):
            chunks.append(c)
        assert "".join(chunks) == "你好"

    import asyncio

    asyncio.run(run())


def test_api_error():
    async def handler(request):
        return httpx.Response(500, json={"detail": "boom"})

    client = _client(handler)

    async def run():
        with pytest.raises(EcoApiError) as ei:
            await client.version()
        assert ei.value.status_code == 500

    import asyncio

    asyncio.run(run())


def test_connection_error():
    client = EcoClient(base_url="http://127.0.0.1:1")

    async def run():
        with pytest.raises(EcoConnectionError):
            await client.version()

    import asyncio

    asyncio.run(run())


def test_memory_types():
    client = _client(
        _json_handler(
            {
                "nodes": [{"id": "n1", "type": "statute", "title": "法典第1054条", "score": 88}],
            }
        )
    )

    async def run():
        nodes = await client.memory_nodes()
        assert len(nodes) == 1
        assert nodes[0].title == "法典第1054条"
        assert nodes[0].score == 88.0

    import asyncio

    asyncio.run(run())


def test_skills_types():
    client = _client(
        _json_handler(
            {
                "skills": [{"name": "fagui-query", "manifest": {"description": "法规速查", "tags": ["law"]}}],
            }
        )
    )

    async def run():
        skills = await client.list_skills()
        assert skills[0].name == "fagui-query"
        assert skills[0].description == "法规速查"

    import asyncio

    asyncio.run(run())


def test_tools_types():
    client = _client(
        _json_handler(
            {
                "tools": [
                    {
                        "source": "govmcp",
                        "name": "env_query_air_quality",
                        "description": "查询空气质量",
                        "category": "环境监测-大气",
                        "tags": [],
                        "approval_required": False,
                    }
                ],
            }
        )
    )

    async def run():
        tools = await client.list_tools()
        assert tools[0].name == "env_query_air_quality"
        assert tools[0].category == "环境监测-大气"

    import asyncio

    asyncio.run(run())


def test_sync_client():
    """SyncEcoClient 委托异步方法（注入 mock client 验证同步语义）。"""
    from eco_agent_sdk import SyncEcoClient

    client = _client(_json_handler({"version": "5.0.0a8"}))
    sync_client = SyncEcoClient(base_url="http://test")
    sync_client._client = client  # 注入 mock，复用驱动 loop

    try:
        v = sync_client.version()
        assert v.version == "5.0.0a8"
    finally:
        sync_client.close()
