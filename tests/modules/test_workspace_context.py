#!/usr/bin/env python3
"""tests/modules/test_workspace_context.py — 工作空间联动上下文注入测试

覆盖：前端工作空间选择器值随 ChatRequest.workspace 传入后，
_dynamic_prompt_sections 注入 context.workspace 片段（空值不注入）。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

import server.api.chat as chat_mod  # noqa: E402
from server.api.chat import _dynamic_prompt_sections  # noqa: E402


class _DummyEng:
    """prompt engine 桩：_dynamic_prompt_sections 只读 eng.phase"""

    phase = "general"


@pytest.fixture(autouse=True)
def _stub_mcp(monkeypatch):
    """MCP 工具发现打桩为空，避免离线环境下触碰外部服务"""
    monkeypatch.setattr(chat_mod, "_mcp_tool_defs", lambda: [])


def _section_ids(sections):
    return [s["section_id"] for s in sections]


def test_workspace_section_injected():
    """workspace='娄底市大气监测' 时必须产出 context.workspace 片段且内容含该名称"""
    sections = _dynamic_prompt_sections("查询空气质量", _DummyEng(), "default", "娄底市大气监测")
    assert "context.workspace" in _section_ids(sections)
    sec = next(s for s in sections if s["section_id"] == "context.workspace")
    assert "娄底市大气监测" in sec["content"]
    assert "娄底市大气监测" in sec["title"]


def test_workspace_section_absent_when_empty():
    """workspace 为空串时不产出该片段"""
    sections = _dynamic_prompt_sections("查询空气质量", _DummyEng(), "default", "")
    assert "context.workspace" not in _section_ids(sections)


def test_workspace_section_absent_by_default():
    """不传 workspace 参数（默认 ''）时同样不产出该片段"""
    sections = _dynamic_prompt_sections("查询空气质量", _DummyEng(), "default")
    assert "context.workspace" not in _section_ids(sections)
