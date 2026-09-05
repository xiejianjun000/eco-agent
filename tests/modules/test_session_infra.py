#!/usr/bin/env python3
"""
tests/modules/test_session_infra.py — 记忆基础设施测试（含故障注入）

覆盖: SessionEventLog 追加/重放/校验链/截断恢复；
      ContextCompactor 降级压缩与 D-03 压缩比；
      MemoryCurator 遗忘曲线 + 矛盾检测/24h 消解。
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

# ═══════════════ SessionEventLog ═══════════════


@pytest.fixture()
def log(tmp_path):
    from agent_core.session_log import SessionEventLog

    return SessionEventLog("s1", base_dir=tmp_path)


def test_append_and_replay(log):
    log.append("user/message", {"content": "你好"})
    log.append("tool/result", {"tool": "file_read", "result": "ok"})
    events = list(log.replay())
    assert len(events) == 2
    assert events[0]["seq"] == 1
    assert events[1]["seq"] == 2
    assert events[0]["data"]["content"] == "你好"


def test_verify_chain_ok(log):
    for i in range(5):
        log.append("tool/result", {"i": i})
    v = log.verify()
    assert v["ok"] is True
    assert v["events"] == 5
    assert v["truncated"] == 0


def test_fault_injection_truncated_tail(log):
    """故障注入：尾部写入半行损坏 → verify 报截断但前序链完整。"""
    for i in range(3):
        log.append("tool/result", {"i": i})
    # 模拟崩溃留下的半行
    with log.path.open("a", encoding="utf-8") as f:
        f.write('{"seq": 4, "type": "tool/resu')  # 不完整 JSON
    v = log.verify()
    assert v["ok"] is True
    assert v["events"] == 3
    assert v["truncated"] == 1
    # 截断后可继续追加（seq 从 4 继续）
    seq = log.append("tool/result", {"recovered": True})
    assert seq == 4


def test_fault_injection_hash_tamper(log):
    """故障注入：篡改中间事件 data → hash 校验失败。"""
    for i in range(3):
        log.append("tool/result", {"i": i})
    lines = log.path.read_text(encoding="utf-8").splitlines()
    # 篡改第 2 条（seq=2）的 data 字段
    import json

    e2 = json.loads(lines[1])
    e2["data"] = {"tampered": True}
    lines[1] = json.dumps(e2, ensure_ascii=False)
    log.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    v = log.verify()
    assert v["ok"] is False
    assert "hash 校验失败" in v["error"]


def test_replay_is_deterministic(log):
    for i in range(3):
        log.append("user/message", {"i": i})
    first = [(e["seq"], e["hash"]) for e in log.replay()]
    second = [(e["seq"], e["hash"]) for e in log.replay()]
    assert first == second


# ═══════════════ ContextCompactor ═══════════════


def test_compaction_truncate_fallback():
    from agent_core.compaction import compact, estimate_tokens

    msgs = [{"role": "user", "content": f"第{i}条消息 " + "内容" * 200} for i in range(20)]
    tokens_before = estimate_tokens(msgs)
    result = compact(msgs, max_tokens=tokens_before // 3)
    assert result["method"] == "truncate"  # 无 LLM → 降级
    assert result["tokens_after"] < result["tokens_before"]
    # D-03 口径：压缩比 < 50%
    assert result["tokens_after"] / result["tokens_before"] < 0.5
    # 尾部保留
    assert result["messages"][-1]["content"] == msgs[-1]["content"]


def test_compaction_noop_under_limit():
    from agent_core.compaction import compact

    msgs = [{"role": "user", "content": "短消息"}]
    result = compact(msgs, max_tokens=8000)
    assert result["method"] == "noop"
    assert result["messages"] == msgs


# ═══════════════ MemoryCurator ═══════════════


def test_retention_curve_ebbinghaus():
    from agent_core.memory_curation import MemoryCurator

    assert MemoryCurator.retention_weight(0) == pytest.approx(1.0)
    assert MemoryCurator.retention_weight(86400) == pytest.approx(1 / math.e, rel=0.01)
    assert MemoryCurator.retention_weight(86400 * 3) < 0.1  # 3 天后接近遗忘
    assert MemoryCurator.retention_weight(86400 * 30, permanent=True) == 1.0  # 永久豁免


def test_recall_orders_by_retention():
    from datetime import datetime, timedelta

    from agent_core.memory_curation import MemoryCurator

    now = datetime.now()
    episodic = [
        {"event": "旧事件", "timestamp": (now - timedelta(days=10)).isoformat()},
        {"event": "新事件", "timestamp": (now - timedelta(hours=1)).isoformat()},
        {"event": "永久事件", "timestamp": (now - timedelta(days=5)).isoformat(), "permanent": True},
    ]
    curator = MemoryCurator(tmp_path_fixture())
    scored = curator.score_episodic(episodic, now=now)
    assert scored[0]["status"] == "forgotten"  # 10 天前
    assert scored[1]["status"] == "active"
    assert scored[2]["status"] == "active" and scored[2]["retention_weight"] == 1.0


def test_conflict_detect_and_24h_resolve(tmp_path):
    from datetime import datetime, timedelta

    from agent_core.memory_curation import MemoryCurator

    curator = MemoryCurator(tmp_path)
    # 语义层：同 key 先登记旧值
    curator.register_value("法规.大气法.处罚幅度", "十万以上一百万以下")
    semantic = {"法规.大气法.处罚幅度": {"value": "十万以上一百万以下", "updated_at": None}}
    conflicts = curator.detect_conflicts(semantic)
    assert conflicts == []  # 无冲突

    # 值变了 → 检测到矛盾
    semantic["法规.大气法.处罚幅度"] = {"value": "二十万以上二百万以下", "updated_at": None}
    conflicts = curator.detect_conflicts(semantic)
    assert len(conflicts) == 1
    assert conflicts[0]["status"] == "open"

    # 未到 24h 不消解
    r = curator.resolve_conflicts(semantic)
    assert r["resolved"] == 0

    # 模拟已过 24h：把 registered_at 拨回 25 小时前
    data = json_loads(curator._conflicts_path)
    data[0]["registered_at"] = (datetime.now() - timedelta(hours=25)).isoformat()
    curator._save_conflicts(data)
    r = curator.resolve_conflicts(semantic)
    assert r["resolved"] == 1
    stats = curator.stats()
    assert stats["open_conflicts"] == 0
    assert stats["audit_entries"] >= 1


def test_conflict_permanent_not_resolved_automatically(tmp_path):
    """permanent 事实的矛盾需人工裁决，不自动消解。"""
    from datetime import datetime, timedelta

    from agent_core.memory_curation import MemoryCurator

    curator = MemoryCurator(tmp_path)
    curator.register_value("法典.施行日", "2026-08-15", permanent=True)
    data = json_loads(curator._conflicts_path)
    data[0]["registered_at"] = (datetime.now() - timedelta(hours=25)).isoformat()
    curator._save_conflicts(data)
    r = curator.resolve_conflicts({})  # 语义层为空（外部源）
    # permanent 矛盾保持 open，等待人工裁决
    assert r["open"] == 1


# ═══════════════ 辅助 ═══════════════


def tmp_path_fixture():
    import tempfile

    return Path(tempfile.mkdtemp(prefix="eco-mem-"))


def json_loads(path):
    import json

    return json.loads(path.read_text(encoding="utf-8"))


import math  # noqa: E402  (retention 测试用)
