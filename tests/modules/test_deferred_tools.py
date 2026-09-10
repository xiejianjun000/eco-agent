"""连接器延迟工具代理（对标 WorkBuddy ToolSearch / DeferExecuteTool）单测。

不连真实 MCP：注入 fake handler 与 fake manager，验证发现/打分、
只读拦截、非连接器拒绝、真实目标透传四条安全与功能路径。
"""

from __future__ import annotations

import asyncio
import json

import pytest

from agent_core import deferred_tools as dt
from agent_core import tools_registry as tr


class FakeMgr:
    def __init__(self, tools):
        self._tools = tools

    def all_tools(self):
        return [{"server": s, "name": n, "description": d} for s, n, d in self._tools]


FAKE_TOOLS = [
    ("tencent_docs", "query_space_list", "查询腾讯文档空间列表"),
    ("tencent_docs", "doc_insert_rows", "向文档插入行（写）"),
    ("tencent_docs", "create_space", "创建腾讯文档空间"),
    ("eia-law", "search_keyword_policy", "法规关键词检索 policy"),
]


def _run_sync(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


@pytest.fixture()
def fake_mgr(monkeypatch):
    # 单测只验代理机制；权限闸门口径由 test_permissions 覆盖
    monkeypatch.setenv("ECO_PERMISSION_GATE", "0")
    mgr = FakeMgr(FAKE_TOOLS)
    for s, n, _ in FAKE_TOOLS:
        slug = tr.normalize_tool_name(f"mcp__{s}__{n}")
        tr._HANDLERS[slug] = lambda server=s, tool=n, **kw: {
            "success": True, "is_error": False, "text": f"{server}/{tool} ok", "server": server,
        }
    monkeypatch.setattr(dt, "_manager", lambda: mgr)
    # defer 内部会调 tr.attach_mcp_tools() 触发远程连接，单测里置为 no-op
    monkeypatch.setattr(tr, "attach_mcp_tools", lambda *a, **k: [])
    dt.register_deferred_tools()
    yield mgr
    for s, n, _ in FAKE_TOOLS:
        tr._HANDLERS.pop(tr.normalize_tool_name(f"mcp__{s}__{n}"), None)


# ── ToolSearch ──────────────────────────────────────────────────────
def test_search_ranks_by_keyword(fake_mgr):
    r = json.loads(dt.tool_search("法规 检索 policy"))
    assert r["ok"] is True and r["count"] >= 1
    assert r["results"][0]["server"] == "eia-law"


def test_search_server_filter(fake_mgr):
    r = json.loads(dt.tool_search("", server="eia-law"))
    assert r["count"] >= 1
    assert all(x["server"] == "eia-law" for x in r["results"])


def test_search_empty_query_lists_all(fake_mgr):
    r = json.loads(dt.tool_search("", limit=30))
    assert r["total_connected_tools"] == len(FAKE_TOOLS)


def test_search_no_connector(monkeypatch):
    monkeypatch.setattr(dt, "_manager", lambda: None)
    r = json.loads(dt.tool_search("x"))
    assert r["ok"] is False and "连接器" in r["note"]


# ── DeferExecuteTool ────────────────────────────────────────────────
def test_defer_rejects_non_mcp(fake_mgr):
    out = json.loads(_run_sync(dt.defer_execute_tool("file_write", {})))
    assert out["ok"] is False and "连接器工具" in out["error"]


def test_defer_passthrough_read_tool(fake_mgr):
    out = json.loads(_run_sync(dt.defer_execute_tool("mcp__tencent_docs__query_space_list", {})))
    assert out["ok"] is True
    assert out["target_tool"].endswith("query_space_list")
    assert out["result"].get("success") is True


def test_defer_readonly_blocks_write(fake_mgr):
    tok = dt.set_readonly(True)
    try:
        out = json.loads(_run_sync(dt.defer_execute_tool("mcp__tencent_docs__doc_insert_rows", {})))
        assert out["ok"] is False and "只读" in out["error"]
    finally:
        dt.reset_readonly(tok)


def test_defer_readonly_allows_read(fake_mgr):
    tok = dt.set_readonly(True)
    try:
        out = json.loads(_run_sync(dt.defer_execute_tool("mcp__tencent_docs__query_space_list", {})))
        assert out["ok"] is True
    finally:
        dt.reset_readonly(tok)


def test_defer_unknown_tool(fake_mgr):
    out = json.loads(_run_sync(dt.defer_execute_tool("mcp__nope__ghost", {})))
    assert out["ok"] is False and "不可用" in out["error"]


def test_readonly_verb_detection():
    assert dt._is_readonly_tool("mcp__tencent_docs__query_space_list") is True
    assert dt._is_readonly_tool("mcp__tencent_docs__doc_insert_rows") is False
    assert dt._is_readonly_tool("file_write") is False
