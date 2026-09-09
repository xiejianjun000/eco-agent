#!/usr/bin/env python3
"""tests/modules/test_spec_event_protocol.py — 事件协议双写

规格要求的事件集合：
    think / tool_call / tool_result / content_chunk / final / error / status

eco 历史上用的是自己一套：
    think / think_delta / tool_start / tool / answer / narration /
    correction / card / artifact

直接改名会一次性打碎前端（ChatView.tsx、turnFold.ts、每工具视图、
展开面板全按 tool_start/tool/answer 匹配），故采用双写：
原 type 保持不变，额外附 spec_type。本文件锁死这层映射，
并守住「不猜未知类型」与「不改动原字段」两条底线。
"""

from __future__ import annotations

import pytest

from server.api.chat import _SPEC_EVENT_MAP, _with_spec_type

SPEC_TYPES = {"think", "tool_call", "tool_result", "content_chunk",
              "final", "error", "status"}


# ── 映射结果必须落在规格集合内 ────────────────────────────────────
def test_every_mapping_target_is_a_spec_type():
    """映射表右侧不得出现规格未定义的事件名。"""
    unknown = set(_SPEC_EVENT_MAP.values()) - SPEC_TYPES
    assert unknown == set(), f"映射到了规格外的事件名: {unknown}"


@pytest.mark.parametrize("native,spec", [
    ("think", "think"),
    ("think_delta", "think"),
    ("tool_start", "tool_call"),
    ("tool", "tool_result"),
    ("answer", "final"),
    ("error", "error"),
    ("narration", "status"),
    ("correction", "status"),
])
def test_core_mappings(native, spec):
    """核心事件逐条对齐（改动即回归）。"""
    out = _with_spec_type({"type": native, "round": 1})
    assert out["spec_type"] == spec


# ── 双写语义：不动原字段 ─────────────────────────────────────────
def test_original_type_is_preserved():
    """原 type 必须原样保留 —— 前端仍按它匹配。"""
    out = _with_spec_type({"type": "tool_start", "name": "query_air_quality"})
    assert out["type"] == "tool_start"
    assert out["name"] == "query_air_quality"


def test_input_event_is_not_mutated():
    """不得就地修改入参（事件对象同时也进 trace 落盘）。"""
    ev = {"type": "tool", "name": "grep"}
    _with_spec_type(ev)
    assert "spec_type" not in ev, "污染了原事件对象"


def test_all_original_fields_survive():
    ev = {"type": "tool", "name": "shell_run", "duration_ms": 31,
          "result_preview": "x", "round": 2}
    out = _with_spec_type(ev)
    for k, v in ev.items():
        assert out[k] == v


# ── 未知类型：宁可缺字段，也不猜错 ────────────────────────────────
def test_unknown_type_gets_no_spec_type():
    """未收录类型不加 spec_type —— 避免客户端据错误映射做分支。"""
    out = _with_spec_type({"type": "某个未来新增的事件"})
    assert "spec_type" not in out


def test_missing_type_is_safe():
    out = _with_spec_type({"round": 1})
    assert "spec_type" not in out


@pytest.mark.parametrize("bad", [None, "字符串", 123, []])
def test_non_dict_passes_through(bad):
    """非 dict 原样返回，不抛错（事件源理论上不该给，但不能崩）。"""
    assert _with_spec_type(bad) is bad


# ── 覆盖面：eco 实际会发的事件都要有映射 ──────────────────────────
def test_all_emitted_event_types_are_mapped():
    """代码里真实发射过的事件类型必须都在映射表里。

    漏一个就意味着按规格消费的客户端会收到没有 spec_type 的事件。
    """
    import re
    from pathlib import Path

    src = Path(__file__).resolve().parents[2] / "server" / "api" / "chat.py"
    text = src.read_text(encoding="utf-8")
    # 只取轨迹事件构造处：_emit({"type": "..."}) 与 {"type": "...", "round"
    emitted = set(re.findall(r'_emit\(\{\s*"type":\s*"([a-z_]+)"', text))
    emitted |= set(re.findall(r'\{"type":\s*"([a-z_]+)",\s*"round"', text))
    missing = emitted - set(_SPEC_EVENT_MAP)
    assert missing == set(), f"这些实际发射的事件没有规格映射: {missing}"
