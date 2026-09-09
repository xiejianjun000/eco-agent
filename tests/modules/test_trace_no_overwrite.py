#!/usr/bin/env python3
"""tests/modules/test_trace_no_overwrite.py — 轨迹文件不得互相覆盖

为什么有这个文件（真实事故，不是假想）：

  军哥定的验收协议是「他发提示词、我在后台看日志和轨迹、他把输出发我核对」。
  一次六条探针的人工验收里，我核完第 1 条读到「5.82s、单个 round1 span」，
  等他发到第 3 条时回头再读同一文件，内容已经变成排污许可的 3 个 span ——
  **前面几条的轨迹证据全部丢失，无法回溯**。

  根因：SpanTree.save() 的文件名只有 session_id。
  Web 端同一会话连续对话时，每轮都写同一个路径，后一轮覆盖前一轮。

  为什么不能用 trace_id 当判别式：trace_id_for_session() 是
  uuid5(NAMESPACE_URL, f"eco:{session_id}") 的**确定性派生**，
  同一会话每轮完全相同，加进文件名照样覆盖。
  我一开始就想用它，读了实现才发现不行 —— 记在这里免得下次重犯。

  现方案：文件名带首个 span 的 UTC 起始时间戳。同一会话内单调递增，
  天然按轮次排序，不引入新状态。
"""

from __future__ import annotations

import time

from agent_core.observability import SpanTree


def _tree_with_span(session_id: str, name: str) -> SpanTree:
    t = SpanTree(session_id)
    t.start(name, kind="llm_call")
    t.end()
    return t


def test_two_rounds_same_session_do_not_overwrite(tmp_path):
    """同一 session 连续两轮，必须落成两个文件。"""
    first = _tree_with_span("web-abc", "round1")
    p1 = first.save(tmp_path)
    assert p1 is not None and p1.is_file()

    # 时间戳精度到秒，确保第二轮落在不同的秒上
    time.sleep(1.1)

    second = _tree_with_span("web-abc", "round1")
    p2 = second.save(tmp_path)
    assert p2 is not None and p2.is_file()

    assert p1 != p2, (
        f"同一 session 两轮写到了同一路径 {p1.name} —— 前一轮证据已被覆盖")
    assert len(list(tmp_path.glob("*.json"))) == 2


def test_unique_session_id_keeps_plain_name(tmp_path):
    """session_id 本来唯一时（CLI 侧自带时间戳），命名不得被改动。

    CLI 的 session_id 形如 20260909-210540-32d0af，本身已唯一；
    给它再加时间戳属于过度修改，也会打破既有 API 契约。
    """
    t = _tree_with_span("20260909-210540-32d0af", "root")
    p = t.save(tmp_path)
    assert p is not None
    assert p.name == "20260909-210540-32d0af.json", p.name


def test_same_tree_saved_twice_updates_in_place(tmp_path):
    """同一棵树重复 save 应就地更新，不产生第二个文件。"""
    t = _tree_with_span("web-abc", "round1")
    p1 = t.save(tmp_path)
    p2 = t.save(tmp_path)
    assert p1 == p2, "同一棵树重复落盘产生了多个文件"
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_filename_keeps_session_id_prefix(tmp_path):
    """文件名仍以 session_id 开头，保证能按会话 glob 检索。

    验收时要靠 session_id 定位某次对话的全部轮次，
    前缀一旦丢失，「按会话回溯」就无从下手。
    """
    t = _tree_with_span("web-xyz-123", "round1")
    p = t.save(tmp_path)
    assert p is not None
    assert p.name.startswith("web-xyz-123"), p.name
    assert list(tmp_path.glob("web-xyz-123*.json")), "无法按 session_id 前缀检索"


def test_empty_tree_falls_back_to_plain_session_id(tmp_path):
    """无 span 的空树用纯 session_id —— 空树没有回溯价值。"""
    t = SpanTree("web-empty")
    p = t.save(tmp_path)
    assert p is not None
    assert p.name == "web-empty.json", p.name


def test_saved_content_is_this_round_only(tmp_path):
    """每个文件只含本轮的 span，不得混入其它轮。"""
    import json

    a = SpanTree("web-mix")
    a.start("roundA", kind="llm_call")
    a.end()
    pa = a.save(tmp_path)

    time.sleep(1.1)

    b = SpanTree("web-mix")
    b.start("roundB", kind="llm_call")
    b.end()
    pb = b.save(tmp_path)

    names_a = [s["name"] for s in json.loads(pa.read_text(encoding="utf-8"))["spans"]]
    names_b = [s["name"] for s in json.loads(pb.read_text(encoding="utf-8"))["spans"]]
    assert names_a == ["roundA"], names_a
    assert names_b == ["roundB"], names_b
