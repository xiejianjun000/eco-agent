#!/usr/bin/env python3
"""
tests/modules/test_web_session_continuity.py — Web 会话连续性补全测试

覆盖本轮两处改动：
  1. server/api/chat.py：Web 会话每轮落检查点（_auto_checkpoint，与 CLI 同语义），
     一轮对话后 GET /api/v1/checkpoints/{sid} 可见、可 rewind。
  2. server/api/chat.py + sessions.py：trace 摘要与 usage 随 assistant/message
     入 session_log（SHA-256 链），GET /sessions/{sid}/messages 重放时一并返回，
     且哈希链 verify 仍通过。

conftest 已将 HOME 重定向到临时目录（检查点落 ~/.eco/checkpoints 进临时 HOME）；
session_log 默认落仓库 memory-tree/data/，这里用 monkeypatch 指到 tmp_path 隔离。
"""

from __future__ import annotations

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


@pytest.fixture()
def isolated_log(tmp_path, monkeypatch):
    """session_log 落盘目录指到 tmp_path，避免污染仓库 memory-tree/data/。"""
    import agent_core.session_log as slog_mod

    monkeypatch.setattr(slog_mod, "DATA_DIR", tmp_path)
    return tmp_path


# ── 1. Web 会话每轮落检查点 ─────────────────────────────
def test_web_chat_creates_checkpoint_per_turn(client, isolated_log):
    sid = "wsc-ckpt"
    r = client.post("/api/v1/chat", json={
        "message": "你好", "history": [], "session_id": sid})
    assert r.status_code == 200

    r = client.get(f"/api/v1/checkpoints/{sid}")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] >= 1
    # 第 1 个检查点 = 第 1 轮用户输入前快照（历史为空）
    assert data["items"][0]["id"] == 1
    assert data["items"][0]["history_len"] == 0

    # 第二轮（带上一轮历史）→ 检查点 #2 含 2 条历史
    r = client.post("/api/v1/chat", json={
        "message": "继续", "session_id": sid,
        "history": [{"role": "user", "content": "你好"},
                    {"role": "assistant", "content": "你好！有什么可以帮你？"}]})
    assert r.status_code == 200
    data = client.get(f"/api/v1/checkpoints/{sid}").json()
    ids = [c["id"] for c in data["items"]]
    assert ids == [1, 2]
    assert data["items"][1]["history_len"] == 2

    # rewind 到 #1：返回第 1 轮提问前的历史（空），并截断其后检查点
    r = client.post(f"/api/v1/checkpoints/{sid}/rewind", json={"n": 1})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["history"] == []
    ids = [c["id"] for c in client.get(f"/api/v1/checkpoints/{sid}").json()["items"]]
    assert ids == [1]


# ── 2. trace/usage 随消息入链，恢复时回放 ───────────────
def test_persisted_turn_restores_trace_and_usage(client, isolated_log):
    from agent_core.session_log import SessionEventLog
    from server.api.chat import _persist_turn

    sid = "wsc-trace"
    trace = [
        {"type": "think", "round": 1, "thought": "先查法条再回答", "cost_ms": 120},
        {"type": "tool", "round": 1, "name": "statute_lookup",
         "args": {"article": "1054"}, "result_preview": "第一千零五十四条…", "cost_ms": 30},
        {"type": "card", "round": 1, "title": "趋势图", "html": "<html>大体积</html>"},
        {"type": "answer", "round": 1, "chars": 42, "cost_ms": 800},
    ]
    usage = {"prompt_tokens": 100, "completion_tokens": 42, "total_tokens": 142}
    _persist_turn(sid, "第1054条说了什么", "第一千零五十四条规定…", ok=True,
                  trace=trace, usage=usage, duration_ms=950, ttft_ms=120)

    # 哈希链 verify 仍通过（data 扩展字段纳入签名，不破坏既有校验）
    v = SessionEventLog(f"web/{sid}").verify()
    assert v["ok"] is True

    r = client.get(f"/api/v1/sessions/{sid}/messages")
    assert r.status_code == 200
    msgs = r.json()["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    amsg = msgs[1]
    assert amsg["usage"] == usage
    assert amsg["duration_ms"] == 950 and amsg["ttft_ms"] == 120
    # 过程块事件保留（think/tool/answer 完成态），card 的 html 不持久化
    types = [e["type"] for e in amsg["trace"]]
    assert types == ["think", "tool", "card", "answer"]
    assert amsg["trace"][0]["thought"] == "先查法条再回答"
    assert "html" not in amsg["trace"][2]


def test_trace_for_log_truncates_long_strings():
    from server.api.chat import _trace_for_log

    out = _trace_for_log([
        {"type": "think", "thought": "长" * 5000},
        {"type": "tool", "name": "x", "result_preview": "短"},
        "not-a-dict",
    ])
    assert len(out) == 2
    assert len(out[0]["thought"]) < 2100 and "truncated" in out[0]["thought"]
    assert out[1]["result_preview"] == "短"


def test_failed_turn_keeps_user_message_only(client, isolated_log):
    """失败轮次（ok=False）：只落 user/message，不落 assistant/trace——
    恢复时不会把失败回复当作带轨迹的助手消息。"""
    from server.api.chat import _persist_turn

    sid = "wsc-fail"
    _persist_turn(sid, "会失败的问题", "", ok=False,
                  trace=[{"type": "think", "thought": "x"}],
                  usage={"total_tokens": 1})
    msgs = client.get(f"/api/v1/sessions/{sid}/messages").json()["messages"]
    assert [m["role"] for m in msgs] == ["user"]
