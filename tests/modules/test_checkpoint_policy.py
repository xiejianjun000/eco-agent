"""checkpoint_policy 与断尾修复测试（对标 DSH fail-closed checkpoint + torn-tail repair）"""

from pathlib import Path

from agent_core.checkpoint_policy import SessionDurabilityError, durable_guard, requires_durable
from agent_core.session_log import SessionEventLog


def _mklog(tmp_path: Path, sid: str = "t1") -> SessionEventLog:
    slog = SessionEventLog(sid, base_dir=tmp_path)
    slog.append("user/message", {"content": "hi"})
    slog.append("assistant/message", {"content": "ok"})
    return slog


def test_requires_durable_semantics():
    assert requires_durable("llm/request")
    assert requires_durable("tool/call")
    assert not requires_durable("system/start")


def test_durable_guard_passes_on_clean_log(tmp_path):
    slog = _mklog(tmp_path)
    durable_guard(slog, "llm/request")  # 不抛即通过


def test_repair_torn_tail(tmp_path):
    slog = _mklog(tmp_path)
    with slog.path.open("a", encoding="utf-8") as f:
        f.write('{"seq": 99, "partial')  # 模拟崩溃半行
    v = slog.verify()
    assert v.get("truncated", 0) >= 1
    r = slog.repair_torn_tail()
    assert r["repaired"] is True and r["dropped_lines"] >= 1
    v2 = slog.verify()
    assert v2["ok"] is True and v2.get("truncated", 0) == 0
    # 修复审计事件已入链
    types = [e["type"] for e in slog.replay()]
    assert "system/repair" in types


def test_durable_guard_repairs_then_passes(tmp_path):
    slog = _mklog(tmp_path)
    with slog.path.open("a", encoding="utf-8") as f:
        f.write('{"seq": 5, "broken')
    durable_guard(slog, "tool/call")  # 自动修复后放行


def test_durable_guard_fail_closed_on_mid_corruption(tmp_path):
    """中部损坏（非断尾）无法修复 → 守卫抛错阻断（fail-closed）。"""
    slog = _mklog(tmp_path)
    lines = slog._raw_lines()
    # 篡改中间一条的 hash
    bad = lines[0].replace(lines[0][-10:-2], "deadbeef")
    slog.path.write_text("\n".join([bad, lines[1]]) + "\n", encoding="utf-8")
    try:
        durable_guard(slog, "llm/request")
        raise AssertionError("应当抛 SessionDurabilityError")
    except SessionDurabilityError:
        pass
