"""性能冒烟：无网络确定性快速检查（quality-gate 门禁）。本地纯 CPU / 临时目录路径，避免 CI 抖动。"""

import time

from agent_core import cost_ledger, eco_peer, schema_guard


def test_schema_guard_1000_ops_fast():
    """1000 次 schema 校验应在数秒内完成（本地纯 CPU）。"""
    schema = {
        "type": "object",
        "properties": {"a": {"type": "integer"}, "b": {"type": "string"}},
        "required": ["a"],
    }
    t0 = time.perf_counter()
    for i in range(1000):
        ok, _ = schema_guard.SchemaGuard.validate({"a": i, "b": "x"}, schema)
        assert ok
    dt = time.perf_counter() - t0
    assert dt < 5.0, f"schema guard too slow: {dt:.2f}s"


def test_peer_register_create_send(tmp_path):
    """PeerBus 注册+建房+发送在临时目录瞬时完成。"""
    bus = eco_peer.PeerBus(str(tmp_path / ".eco"))
    bus.register_peer("perfA", "http://a")
    bus.register_peer("perfB", "http://b")
    room = bus.create_room("room1", ["perfA", "perfB"])
    t0 = time.perf_counter()
    msg = bus.send(room["id"], "perfA", "hi")
    dt = time.perf_counter() - t0
    assert msg is not None
    assert dt < 2.0, f"peer send too slow: {dt:.2f}s"


def test_cost_ledger_summary_empty():
    """空 ledger summary 不抛错且字段齐全。"""
    ledger = cost_ledger.CostLedger()
    s = ledger.summary()
    assert isinstance(s, dict)
    assert "delegations" in s
