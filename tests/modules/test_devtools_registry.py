#!/usr/bin/env python3
"""
tests/modules/test_devtools_registry.py — devtools 插件接入 LLM 工具表测试

覆盖：插件加载后工具进入 tools_registry（LLM 可见）、
execute_tool 路径执行（含权限闸门 overrides）、卸载后移除。
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import asyncio  # noqa: E402

import pytest  # noqa: E402


@pytest.fixture()
def loaded_devtools():
    """加载 devtools 插件（测试前确保卸载干净，测试后卸载）。"""
    from agent_core.plugins import PluginManager
    from agent_core.tools_registry import unregister_external_tool

    for name in ("shell_run", "file_read", "file_write", "git_status"):
        unregister_external_tool(name)

    mgr = PluginManager()
    result = mgr.load("devtools")
    assert result["ok"] is True, result
    yield mgr
    mgr.unload("devtools")


def test_tools_in_llm_visible_table(loaded_devtools):
    from agent_core.tools_registry import get_tool_names

    names = get_tool_names()
    for expected in ("shell_run", "file_read", "file_write", "git_status"):
        assert expected in names, f"{expected} 未进入 LLM 可见工具表"


def test_execute_file_roundtrip(loaded_devtools, tmp_path, monkeypatch):
    import json

    from agent_core.tools_registry import execute_tool

    monkeypatch.setenv("ECO_PERMISSION_GATE", "1")  # 本文件验证权限行为，需显式开启闸门
    target = tmp_path / "demo.txt"
    result = asyncio.run(execute_tool("file_write", {"path": str(target), "content": "评查内容"}))
    assert json.loads(result)["ok"] is True
    content = asyncio.run(execute_tool("file_read", {"path": str(target)}))
    # execute_tool 对所有返回值统一 JSON 序列化（str 会带引号）
    assert json.loads(content) == "评查内容"


def test_execute_l1_auto_allowed(loaded_devtools, monkeypatch):
    from agent_core.tools_registry import execute_tool

    monkeypatch.setenv("ECO_PERMISSION_GATE", "1")
    result = asyncio.run(execute_tool("git_status", {"repo_path": str(ROOT)}))
    assert "recent_commits" in result  # L1 自动放行并返回真实数据


def test_execute_l3_gated(loaded_devtools, monkeypatch):
    """shell_run 是 L3：白名单外命令被闸门拒绝（返回 permission denied JSON，不执行）。"""
    from agent_core.tools_registry import execute_tool

    monkeypatch.setenv("ECO_PERMISSION_GATE", "1")
    result = asyncio.run(execute_tool("shell_run", {"command": "echo not-whitelisted"}))
    assert "permission denied" in result
    assert "deny" in result


def test_unload_removes_from_table(loaded_devtools):
    from agent_core.tools_registry import get_tool_names

    loaded_devtools.unload("devtools")
    names = get_tool_names()
    for gone in ("shell_run", "file_read", "file_write", "git_status"):
        assert gone not in names, f"{gone} 卸载后仍留在工具表"
