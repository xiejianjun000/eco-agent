#!/usr/bin/env python3
"""
tests/modules/test_server_api.py — eco-server 管理 API 测试

覆盖：应用工厂、健康检查、版本、技能列表、工具目录、记忆统计、
会话创建/查询、对话端点的无 LLM 降级路径。
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from server.app import create_app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    app = create_app()
    with TestClient(app) as c:
        yield c


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "version" in data


def test_version(client):
    r = client.get("/api/v1/version")
    assert r.status_code == 200
    assert "version" in r.json()


def test_skills_list(client):
    r = client.get("/api/v1/skills")
    assert r.status_code == 200
    data = r.json()
    assert "count" in data and "skills" in data


def test_skills_search(client):
    r = client.get("/api/v1/skills/search", params={"q": "执法"})
    assert r.status_code == 200
    data = r.json()
    assert "count" in data


def test_tools_catalog(client):
    r = client.get("/api/v1/tools")
    assert r.status_code == 200
    data = r.json()
    assert "count" in data and "tools" in data and "categories" in data


def test_tools_search(client):
    r = client.get("/api/v1/tools", params={"q": "空气"})
    assert r.status_code == 200
    assert r.json()["count"] >= 0


def test_tools_stats(client):
    r = client.get("/api/v1/tools/stats")
    assert r.status_code == 200
    assert "total" in r.json()


def test_memory_stats(client):
    r = client.get("/api/v1/memory/stats")
    assert r.status_code == 200
    assert "total_nodes" in r.json()


def test_memory_nodes(client):
    r = client.get("/api/v1/memory/nodes", params={"limit": 5})
    assert r.status_code == 200
    data = r.json()
    assert "nodes" in data


def test_sessions_create_and_get(client):
    r = client.post("/api/v1/sessions", json={"user_id": "test-web-user", "user_name": "测试"})
    assert r.status_code == 200
    sid = r.json()["session_id"]
    assert sid.startswith("web_")

    r2 = client.get(f"/api/v1/sessions/{sid}")
    assert r2.status_code == 200
    assert r2.json()["session_id"] == sid

    r3 = client.get("/api/v1/sessions")
    assert r3.status_code == 200
    ids = [s["session_id"] for s in r3.json()]
    assert sid in ids


def test_chat_without_llm_degrades(client):
    """无 LLM 配置时，chat 端点必须返回 200 并给出可读提示而非 500。"""
    r = client.post("/api/v1/chat", json={"message": "你好", "history": []})
    assert r.status_code == 200
    reply = r.json()["reply"]
    assert "eco-server" in reply or len(reply) > 0


def test_chat_stream_without_llm_degrades(client):
    r = client.post("/api/v1/chat/stream", json={"message": "你好", "history": []})
    assert r.status_code == 200
    body = r.text
    assert "data:" in body


def test_system_status(client):
    r = client.get("/api/v1/system")
    assert r.status_code == 200
    data = r.json()
    assert "components" in data


def test_metrics(client):
    r = client.get("/api/v1/metrics")
    assert r.status_code == 200
    assert "llm" in r.json()


def test_execute_code_gated_in_chat(monkeypatch):
    """execute_code 挂入对话循环后：code 形态经沙箱自动放行并真实执行；
    command 形态的非白名单调用仍被闸门拦截。"""
    import asyncio
    import json

    from agent_core.tools_registry import execute_tool

    monkeypatch.setenv("ECO_PERMISSION_GATE", "1")
    # code 形态：沙箱即边界 → 自动放行 + 真实执行
    result = asyncio.run(execute_tool("execute_code", {"code": "print(1+1)", "language": "python"}))
    assert "permission denied" not in result
    payload = json.loads(result)
    assert payload.get("success") is True or "sandbox" in payload
    # command 形态非白名单：仍拒绝
    denied = asyncio.run(execute_tool("execute_code", {"command": "rm -rf /"}))
    assert "permission denied" in denied
