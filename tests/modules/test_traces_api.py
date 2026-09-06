#!/usr/bin/env python3
"""
tests/modules/test_traces_api.py — 观测数据 API 测试

覆盖 server/api/traces.py：
  GET /api/v1/traces               摘要列表（倒序）
  GET /api/v1/traces/{session_id}  完整 span 树（attrs 截断 2000 字符）
  GET /api/v1/decisions            决策时间线（trace_id 过滤 + 分页）
  GET /api/v1/stats/summary        provider/model/日期聚合 + 成本估算 + 计价表
  GET/POST /api/v1/checkpoints/... 检查点列举与回滚

conftest 已将 HOME 重定向到临时目录，traces/decisions/stats/checkpoints
的落盘路径均指向临时 HOME，不污染宿主机 ~/.eco。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from server.app import create_app  # noqa: E402

SID = "apitest-s1"


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def seeded():
    """造一份 trace + decision + stats + checkpoint 数据"""
    from agent_core.observability import SpanTree, _default_traces_dir  # noqa: SLF001

    tree = SpanTree(session_id=SID, meta={"provider": "deepseek", "model": "deepseek-chat"})
    root = tree.start(SID, "session")
    llm = tree.start("deepseek-chat", "llm_call", model="deepseek-chat")
    tool = tree.start("search_kb", "tool_call", args={"q": "法"}, result="敏感原文" * 1000)
    tree.end(tool)
    tree.end(llm, prompt_tokens=12, completion_tokens=5, finish_reason="stop")
    tree.end(root)
    tree.save(_default_traces_dir())

    from agent_core.decisions import record_decision

    record_decision(candidate_tools=3, selected_tools=["search_kb"],
                    finish_reason="tool_calls", model="deepseek-chat", round_idx=1)

    from agent_core.llm_client import record_llm_stat

    record_llm_stat("deepseek", "deepseek-chat", 120.5, 100, 40, path="chat:direct", ok=True)
    record_llm_stat("deepseek", "deepseek-chat", 80.0, path="chat:direct", ok=False)

    from agent_core.checkpoint import CheckpointStore

    store = CheckpointStore(session=SID)
    store.create(history=[{"role": "user", "content": "q1"}])
    store.create(history=[{"role": "user", "content": "q1"},
                          {"role": "assistant", "content": "a1"},
                          {"role": "user", "content": "q2"}])
    return tree.trace_id


# ── traces ──────────────────────────────────────────────
def test_traces_list(client, seeded):
    r = client.get("/api/v1/traces")
    assert r.status_code == 200
    data = r.json()
    item = next((x for x in data["items"] if x["session_id"] == SID), None)
    assert item is not None
    assert item["span_count"] == 3
    assert item["llm_calls"] == 1 and item["tool_calls"] == 1
    assert item["prompt_tokens"] == 12 and item["completion_tokens"] == 5
    assert item["trace_id"] == seeded
    assert item["meta"]["provider"] == "deepseek"
    starts = [x["start"] for x in data["items"]]
    assert starts == sorted(starts, reverse=True)


def test_trace_detail_and_truncation(client, seeded):
    r = client.get(f"/api/v1/traces/{SID}")
    assert r.status_code == 200
    data = r.json()
    assert data["session_id"] == SID
    assert data["trace_id"] == seeded
    spans = {s["kind"]: s for s in data["spans"]}
    tool = spans["tool_call"]
    assert tool["parent_id"] == spans["llm_call"]["span_id"]
    # attrs.result 超长截断（4000 字 → ≤2000 + 截断标记）
    result = tool["attrs"]["result"]
    assert len(result) < 2100 and "truncated" in result
    llm = spans["llm_call"]
    assert llm["attrs"]["model"] == "deepseek-chat"
    assert llm["attrs"]["finish_reason"] == "stop"


def test_trace_detail_404_and_bad_id(client):
    assert client.get("/api/v1/traces/no-such-session").status_code == 404
    assert client.get("/api/v1/traces/..%2F..%2Fetc").status_code in (400, 404, 422)


# ── decisions ───────────────────────────────────────────
def test_decisions_timeline(client, seeded):
    r = client.get("/api/v1/decisions", params={"trace_id": seeded})
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 1
    d = data["items"][0]
    assert d["selected_tools"] == ["search_kb"]
    assert d["finish_reason"] == "tool_calls"
    assert d["trace_id"] == seeded
    assert d["hash"]  # SM3 链哈希随条目返回
    # 分页参数合法
    r2 = client.get("/api/v1/decisions", params={"limit": 1, "offset": 0})
    assert r2.status_code == 200 and len(r2.json()["items"]) == 1


# ── stats ───────────────────────────────────────────────
def test_stats_summary(client, seeded):
    r = client.get("/api/v1/stats/summary")
    assert r.status_code == 200
    data = r.json()
    m = next((x for x in data["by_model"] if x["model"] == "deepseek-chat"), None)
    assert m is not None
    assert m["calls"] >= 2 and m["errors"] >= 1
    assert m["prompt_tokens"] >= 100 and m["completion_tokens"] >= 40
    # 成本 = tokens × 计价表（deepseek-chat: 2/8 元每百万）
    assert m["price_per_m"]["input"] == 2.0 and m["price_per_m"]["rule"] == "exact"
    expected = (m["prompt_tokens"] * 2.0 + m["completion_tokens"] * 8.0) / 1_000_000
    assert abs(m["cost_yuan"] - round(expected, 6)) < 1e-6
    assert data["total"]["calls"] >= 2
    assert data["by_date"] and data["pricing"]["default"]["input"] == 4.0


def test_record_llm_stat_null_tokens_become_zero(seeded):
    """stats 修复：拿不到 usage 显式记 0 而非 null（附 tokens_unknown 标记）"""
    from agent_core.llm_client import STATS_FILE

    lines = [json.loads(ln) for ln in STATS_FILE.read_text(encoding="utf-8").splitlines() if ln.strip()]
    rec = lines[-1]  # seeded 里第二次调用：无 usage + ok=False
    assert rec["prompt_tokens"] == 0 and rec["completion_tokens"] == 0
    assert rec["tokens_unknown"] is True
    assert rec["ok"] is False


# ── checkpoints ─────────────────────────────────────────
def test_checkpoints_list_and_rewind(client):
    """检查点用例自造独立会话（seeded 为函数级，跨用例累积会污染计数）"""
    from agent_core.checkpoint import CheckpointStore

    sid = "apitest-cp"
    store = CheckpointStore(session=sid)
    # 清掉可能的残留（同 HOME 下重跑）
    for cp in store.list():
        store._cp_path(cp["id"]).unlink()  # noqa: SLF001
    store.create(history=[{"role": "user", "content": "q1"}])
    store.create(history=[{"role": "user", "content": "q1"},
                          {"role": "assistant", "content": "a1"},
                          {"role": "user", "content": "q2"}])

    r = client.get(f"/api/v1/checkpoints/{sid}")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 2
    assert [c["id"] for c in data["items"]] == [1, 2]
    assert data["items"][1]["history_len"] == 3

    r2 = client.post(f"/api/v1/checkpoints/{sid}/rewind", json={"n": 1})
    assert r2.status_code == 200
    body = r2.json()
    assert body["ok"] is True and body["checkpoint"]["id"] == 1
    assert body["history"] == [{"role": "user", "content": "q1"}]
    # 回滚后 #2 被删除（新时间线）
    r3 = client.get(f"/api/v1/checkpoints/{sid}")
    assert [c["id"] for c in r3.json()["items"]] == [1]

    assert client.post(f"/api/v1/checkpoints/{sid}/rewind", json={"n": 99}).status_code == 404
    assert client.get("/api/v1/checkpoints/bad%20sid!").status_code in (400, 404, 422)
