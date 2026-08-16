#!/usr/bin/env python3
"""
tests/modules/test_plugins.py — 动态插件系统测试

覆盖：manifest 解析、扫描、热加载、工具注册、冲突拒绝、
权限闸门拒绝（L3 非白名单）、卸载、重载、API 端点。
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from agent_core.plugins import (  # noqa: E402
    PluginManager,
    PluginManifest,
)

# 独立测试目录（不污染仓库 plugins/）
TEST_PLUGINS = ROOT / "tests" / "fixtures" / "plugins"


@pytest.fixture()
def mgr(tmp_path):
    """构造带临时插件目录的 PluginManager。"""
    return PluginManager(plugins_dir=tmp_path)


def _write_plugin(base: Path, name: str, yaml_text: str, handler_text: str) -> Path:
    d = base / name
    d.mkdir(parents=True)
    (d / "plugin.yaml").write_text(yaml_text, encoding="utf-8")
    (d / "handler.py").write_text(handler_text, encoding="utf-8")
    return d


GOOD_YAML = """name: example
version: 0.1.0
description: 示例插件
entry: handler
tools:
  - name: example_echo
    description: 回显
    risk_level: L1
"""

GOOD_HANDLER = '''def load(ctx):
    def echo(text: str) -> str:
        return text
    ctx.register_tool("example_echo", echo, description="回显", risk_level="L1")
    return {"ok": True}

def unload(ctx):
    return {"ok": True}
'''


def test_manifest_parse():
    m = PluginManifest.from_dict({
        "name": "x", "version": "1.2.3", "tools": [{"name": "t1", "risk_level": "L1"}],
        "permissions": {"t1": "L1"},
    })
    assert m.name == "x"
    assert m.version == "1.2.3"
    assert m.tools[0].risk_level == "L1"
    assert m.permissions["t1"] == "L1"


def test_manifest_invalid_risk():
    with pytest.raises(ValueError):
        PluginManifest.from_dict({"name": "x", "tools": [{"name": "t1", "risk_level": "L9"}]})


def test_scan_empty(mgr):
    assert mgr.scan() == []


def test_load_and_list(mgr):
    _write_plugin(mgr.plugins_dir, "example", GOOD_YAML, GOOD_HANDLER)
    scanned = mgr.scan()
    assert scanned[0]["name"] == "example"
    assert scanned[0]["status"] == "available"

    result = mgr.load("example")
    assert result["ok"] is True
    assert "example_echo" in result["tools"]

    info = mgr.get("example")
    assert info["status"] == "loaded"
    assert "example_echo" in info["tools"]


def test_load_missing_plugin(mgr):
    assert mgr.load("nope")["ok"] is False


def test_tool_call_echo(mgr):
    _write_plugin(mgr.plugins_dir, "example", GOOD_YAML, GOOD_HANDLER)
    mgr.load("example")
    assert mgr.call_tool("example_echo", {"text": "你好"}) == "你好"


def test_tool_call_unknown(mgr):
    with pytest.raises(KeyError):
        mgr.call_tool("no_such_tool", {})


def test_unload(mgr):
    _write_plugin(mgr.plugins_dir, "example", GOOD_YAML, GOOD_HANDLER)
    mgr.load("example")
    result = mgr.unload("example")
    assert result["status"] == "unloaded"
    # 卸载后插件回到"available"（磁盘仍在），不再处于 loaded 态
    info = mgr.get("example")
    assert info is not None
    assert info["status"] == "available"
    with pytest.raises(KeyError):
        mgr.call_tool("example_echo", {"text": "x"})


def test_reload(mgr):
    _write_plugin(mgr.plugins_dir, "example", GOOD_YAML, GOOD_HANDLER)
    mgr.load("example")
    result = mgr.reload("example")
    assert result["ok"] is True
    assert result["status"] == "loaded"


def test_conflict_rejected(mgr):
    """两个插件注册同名工具，第二个默认被拒。"""
    _write_plugin(mgr.plugins_dir, "a", GOOD_YAML, GOOD_HANDLER)
    other_yaml = GOOD_YAML.replace("name: example\n", "name: b\n")
    _write_plugin(mgr.plugins_dir, "b", other_yaml, GOOD_HANDLER)
    assert mgr.load("a")["ok"] is True
    result = mgr.load("b")
    assert result["ok"] is False
    assert "冲突" in result["error"]


def test_l3_tool_gated_non_interactive(mgr, monkeypatch):
    """L3 非白名单工具在非交互模式下被权限闸门拒绝。"""
    yaml_text = GOOD_YAML.replace("risk_level: L1", "risk_level: L3")
    handler_text = GOOD_HANDLER.replace('risk_level="L1"', 'risk_level="L3"')
    _write_plugin(mgr.plugins_dir, "example", yaml_text, handler_text)
    mgr.load("example")
    monkeypatch.setenv("ECO_NON_INTERACTIVE", "1")
    with pytest.raises(PermissionError):
        mgr.call_tool("example_echo", {"text": "x"})


def test_api_endpoints(mgr):
    """插件管理 API 端到端（TestClient）。"""
    from fastapi.testclient import TestClient

    from server.app import create_app

    _write_plugin(mgr.plugins_dir, "example", GOOD_YAML, GOOD_HANDLER)
    import agent_core.plugins as plugins_mod

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(plugins_mod, "get_plugin_manager", lambda: mgr)

    app = create_app()
    with TestClient(app) as client:
        r = client.get("/api/v1/plugins")
        assert r.status_code == 200
        assert r.json()["count"] == 1

        r = client.post("/api/v1/plugins/example/load")
        assert r.status_code == 200
        assert r.json()["status"] == "loaded"

        r = client.get("/api/v1/plugins/example")
        assert r.status_code == 200
        assert r.json()["status"] == "loaded"

        r = client.post("/api/v1/plugins/example/unload")
        assert r.status_code == 200
        assert r.json()["status"] == "unloaded"
    monkeypatch.undo()
