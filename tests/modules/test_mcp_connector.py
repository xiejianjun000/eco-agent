#!/usr/bin/env python3
"""
test_mcp_connector.py — mcp_connector 单元测试（全 mock，不依赖远程 MCP server）

覆盖：配置解析 / 优雅降级 / call_tool 成功与统一错误处理 / 超时 /
断线重连重试 / 动态注册进 ReAct 工具体系。
"""

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from agent_core.mcp_connector import (
    DEFAULT_TIMEOUT,
    MCPConnectorManager,
    MCPServerConfig,
    MCPServerConnection,
    load_configs_from_env,
)


def _close_return(value):
    """side_effect 工厂：关闭传入协程并返回固定值"""
    def _f(coro, timeout=None):
        if hasattr(coro, "close"):
            coro.close()
        return value
    return _f


class FakeFuture:
    """模拟 concurrent.futures.Future"""

    def __init__(self, result=None, exc=None):
        self._result = result
        self._exc = exc

    def result(self, timeout=None):
        if self._exc:
            raise self._exc
        return self._result


def make_connection(name="test_srv", tools=None):
    cfg = MCPServerConfig(name=name, transport="sse", url="http://x/sse/")
    conn = MCPServerConnection.__new__(MCPServerConnection)
    conn.config = cfg
    conn._loop = None
    conn._session = None
    conn._cm_stack = []
    conn.tools = tools if tools is not None else [
        {"name": "query_air_quality", "description": "查空气质量", "inputSchema": {}}
    ]
    conn.connected = False
    conn.last_error = ""
    return conn


class FakeContent:
    type = "text"

    def __init__(self, text):
        self.text = text


class FakeResult:
    def __init__(self, text="ok", is_error=False):
        self.content = [FakeContent(text)]
        self.isError = is_error


class TestConfig(unittest.TestCase):
    def test_from_dict_defaults(self):
        cfg = MCPServerConfig.from_dict({"name": "a", "transport": "sse",
                                         "url": "http://x/sse/"})
        self.assertEqual(cfg.timeout, DEFAULT_TIMEOUT)
        self.assertEqual(cfg.command, [])

    def test_load_from_env_json(self):
        payload = '[{"name":"kb","transport":"sse","url":"http://h/sse/"},' \
                  ' {"name":"gov","transport":"stdio","command":["python","s.py"]}]'
        with mock.patch.dict(os.environ, {"ECO_MCP_SERVERS": payload}):
            cfgs = load_configs_from_env()
        self.assertEqual([c.name for c in cfgs], ["kb", "gov"])
        self.assertEqual(cfgs[1].command, ["python", "s.py"])

    def test_load_from_env_empty_and_bad(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ECO_MCP_SERVERS", None)
            self.assertEqual(load_configs_from_env(), [])
        with mock.patch.dict(os.environ, {"ECO_MCP_SERVERS": "{oops"}):
            self.assertEqual(load_configs_from_env(), [])


class TestConnectDegrade(unittest.TestCase):
    """连接失败优雅降级：不抛异常、标记不可用、注册跳过"""

    def test_connect_failure_graceful(self):
        conn = make_connection()
        def refuse(coro, timeout=None):
            if hasattr(coro, "close"):
                coro.close()
            raise RuntimeError("conn refused")
        with mock.patch.object(MCPServerConnection, "_run", side_effect=refuse):
            ok = conn.connect()
        self.assertFalse(ok)
        self.assertFalse(conn.connected)
        self.assertIn("conn refused", conn.last_error)

    def test_connect_success(self):
        conn = make_connection()
        def fake_run(coro, timeout=None):
            coro.close()
            conn.connected = True
            return None
        with mock.patch.object(MCPServerConnection, "_run", side_effect=fake_run):
            self.assertTrue(conn.connect())
        self.assertTrue(conn.connected)


class TestCallTool(unittest.TestCase):
    def test_call_success(self):
        conn = make_connection()
        conn.connected = True
        conn._session = object()
        with mock.patch.object(MCPServerConnection, "_run",
                               side_effect=_close_return(FakeResult('{"aqi": 18}'))):
            r = conn.call_tool("query_air_quality", {"region": "娄底"})
        self.assertTrue(r["success"])
        self.assertEqual(r["text"], '{"aqi": 18}')
        self.assertEqual(r["server"], "test_srv")
        self.assertIn("elapsed_ms", r)

    def test_call_not_connected(self):
        conn = make_connection()
        r = conn.call_tool("t", {})
        self.assertFalse(r["success"])
        self.assertIn("未连接", r["error"])

    def test_call_tool_level_error(self):
        conn = make_connection()
        conn.connected = True
        conn._session = object()
        with mock.patch.object(MCPServerConnection, "_run",
                               side_effect=_close_return(FakeResult("bad", is_error=True))):
            r = conn.call_tool("t", {})
        self.assertFalse(r["success"])
        self.assertTrue(r["is_error"])

    def test_call_timeout_then_reconnect_retry(self):
        """首次调用超时 → 自动重连 → 重试成功"""
        conn = make_connection()
        conn.connected = True
        conn._session = object()
        calls = {"n": 0}

        def fake_run(coro, timeout=None):
            if hasattr(coro, "close"):
                coro.close()
            calls["n"] += 1
            if calls["n"] == 1:
                raise TimeoutError("30s timeout")
            return FakeResult("recovered")

        with mock.patch.object(MCPServerConnection, "_run", side_effect=fake_run), \
             mock.patch.object(MCPServerConnection, "reconnect", return_value=True) as rc:
            r = conn.call_tool("t", {})
        self.assertTrue(r["success"])
        self.assertEqual(r["text"], "recovered")
        rc.assert_called_once()
        self.assertEqual(calls["n"], 2)

    def test_call_reconnect_fails_unified_error(self):
        conn = make_connection()
        conn.connected = True
        conn._session = object()
        def boom(coro, timeout=None):
            if hasattr(coro, "close"):
                coro.close()
            raise TimeoutError("boom")
        with mock.patch.object(MCPServerConnection, "_run", side_effect=boom), \
             mock.patch.object(MCPServerConnection, "reconnect", return_value=False):
            r = conn.call_tool("t", {})
        self.assertFalse(r["success"])
        self.assertIn("TimeoutError", r["error"])


class _FakeReAct:
    def __init__(self):
        self.tools = {}

    def register_tool(self, name, handler, description=""):
        self.tools[name] = (handler, description)


class TestManager(unittest.TestCase):
    def _make_manager(self):
        mgr = MCPConnectorManager.__new__(MCPConnectorManager)
        mgr.configs = []
        mgr._servers = {}
        mgr._loop = None
        mgr._thread = None
        return mgr

    def test_register_into_react_skips_disconnected(self):
        mgr = self._make_manager()
        good = make_connection("govmcp")
        good.connected = True
        bad = make_connection("ehs_kb", tools=[{"name": "kb_search",
                                                "description": "检索", "inputSchema": {}}])
        bad.connected = False
        mgr._servers = {"govmcp": good, "ehs_kb": bad}
        react = _FakeReAct()
        names = mgr.register_into_react(react)
        self.assertEqual(names, ["mcp__govmcp__query_air_quality"])
        self.assertIn("mcp__govmcp__query_air_quality", react.tools)

    def test_registered_handler_calls_through(self):
        mgr = self._make_manager()
        conn = make_connection("govmcp")
        conn.connected = True
        conn._session = object()
        mgr._servers = {"govmcp": conn}
        react = _FakeReAct()
        mgr.register_into_react(react)
        handler, desc = react.tools["mcp__govmcp__query_air_quality"]
        self.assertIn("[MCP:govmcp]", desc)
        with mock.patch.object(MCPServerConnection, "_run",
                               side_effect=_close_return(FakeResult("data"))):
            out = handler(region="娄底")
        self.assertTrue(out["success"])
        self.assertEqual(out["tool"], "query_air_quality")

    def test_call_tool_unknown_server(self):
        mgr = self._make_manager()
        r = mgr.call_tool("nope", "t", {})
        self.assertFalse(r["success"])
        self.assertIn("未知 MCP server", r["error"])

    def test_all_tools_aggregates(self):
        mgr = self._make_manager()
        mgr._servers = {"a": make_connection("a"), "b": make_connection("b")}
        tools = mgr.all_tools()
        self.assertEqual(len(tools), 2)
        self.assertEqual({t["server"] for t in tools}, {"a", "b"})


if __name__ == "__main__":
    unittest.main()
