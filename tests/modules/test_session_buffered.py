"""tests/modules/test_session_buffered.py — SessionEventLog WriteBehind 缓冲批写测试

对标 DSH WriteBehind ≤200ms 语义：
- append_buffered 只进内存队列（不落盘、不 fsync）；
- flush() 一次性批量落盘 + fsync；
- durable() 校验前自动 flush 缓冲；
- 默认 append() 即时 fsync 语义回归不变。
"""

from agent_core.session_log import SessionEventLog


def _mklog(tmp_path, sid: str = "b1") -> SessionEventLog:
    return SessionEventLog(sid, base_dir=tmp_path)


def test_buffered_append_not_visible_until_flush(tmp_path):
    """缓冲追加后 replay 为空：事件只在内存队列，未进盘。"""
    slog = _mklog(tmp_path)
    slog.append_buffered("user/message", {"content": "hi"})
    slog.append_buffered("assistant/message", {"content": "ok"})
    assert list(slog.replay()) == []
    v = slog.verify()
    assert v["ok"] is True and v["events"] == 0
    assert slog.buffered_count() == 2


def test_flush_writes_batch_and_replay_full(tmp_path):
    """flush 后 replay 全量：批量落盘且 hash 链完整可校验。"""
    slog = _mklog(tmp_path)
    slog.append_buffered("user/message", {"content": "hi"})
    slog.append_buffered("assistant/message", {"content": "ok"})
    assert slog.flush() == 2
    events = list(slog.replay())
    assert [e["type"] for e in events] == ["user/message", "assistant/message"]
    assert [e["seq"] for e in events] == [1, 2]
    v = slog.verify()
    assert v["ok"] is True and v["events"] == 2 and v["truncated"] == 0
    # flush 幂等：缓冲已空时再次 flush 为无操作
    assert slog.flush() == 0


def test_durable_auto_flushes_buffer(tmp_path):
    """durable() 校验前自动 flush：内存队列先落盘再校验。"""
    slog = _mklog(tmp_path)
    slog.append_buffered("user/message", {"content": "hi"})
    ok, report = slog.durable()
    assert ok is True
    assert report["events"] == 1  # durable() 内部已先 flush 缓冲
    assert len(list(slog.replay())) == 1  # 事件已落盘可见
    assert slog.buffered_count() == 0


def test_buffered_plus_repair(tmp_path):
    """缓冲 + 断尾修复组合：修复审计事件前先冲刷缓冲，链序与完整性正确。"""
    slog = _mklog(tmp_path)
    slog.append("user/message", {"content": "on disk"})
    slog.append_buffered("assistant/message", {"content": "buffered"})
    # 磁盘尾部注入半行（模拟崩溃残留）
    with slog.path.open("a", encoding="utf-8") as f:
        f.write('{"seq": 99, "partial')
    r = slog.repair_torn_tail()
    assert r["repaired"] is True
    events = list(slog.replay())
    types = [e["type"] for e in events]
    assert "user/message" in types
    assert "assistant/message" in types  # 缓冲事件在修复审计前先冲刷落盘
    assert "system/repair" in types
    v = slog.verify()
    assert v["ok"] is True and v["truncated"] == 0


def test_default_append_immediate_regression(tmp_path):
    """回归：默认 append() 仍即时 fsync 落盘，无需显式 flush。"""
    slog = _mklog(tmp_path)
    slog.append("user/message", {"content": "hi"})
    events = list(slog.replay())
    assert len(events) == 1 and events[0]["type"] == "user/message"
    assert slog.buffered_count() == 0
