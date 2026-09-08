"""增量校验测试。

k6 实测发现：链在压测期间增长（7684→7742），mtime+size 指纹一变缓存作废，
下一个请求扛全量重算 —— eco_audit_ms max 38.9 秒。链每增长一次就有一个
用户等 40 秒。

增量校验只算新增行，但绝不能因此削弱防篡改语义：
追加之后，历史行被改一样要查得出来。
"""
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))


def _chain(tmp_path):
    from agent_core.trace_audit import TraceAudit
    return TraceAudit(base_dir=tmp_path)


def _fill(a, n, prefix="op"):
    for i in range(n):
        a.record_tool_call(tool=f"{prefix}_{i}", args={"i": i},
                           result=str(i), duration_ms=1)


def test_incremental_matches_full(tmp_path):
    """增量结果必须与全量重算完全一致。"""
    a = _chain(tmp_path)
    _fill(a, 30)
    first = a.verify()

    # 再追加，触发增量路径
    _fill(a, 20, prefix="more")
    inc = a.verify()

    # 另起一个实例做全量重算作为参照
    b = _chain(tmp_path)
    full = b.verify()

    assert inc["entries"] == full["entries"] == 50
    assert inc["ok"] == full["ok"]
    assert inc["last_hash"] == full["last_hash"]
    assert len(inc["breaks"]) == len(full["breaks"])
    assert first["entries"] == 30


def test_tamper_after_increment_still_detected(tmp_path):
    """核心安全属性：走过增量路径后，改历史行仍要被查出来。

    如果增量实现把「已验证前缀」无脑信任，改历史就查不出来了 ——
    那等于审计失效。
    """
    a = _chain(tmp_path)
    _fill(a, 20)
    a.verify()          # 建立前缀缓存
    _fill(a, 10, "x")
    a.verify()          # 走增量路径

    # 篡改第 5 行的业务内容
    p = a.chain_path
    lines = p.read_text(encoding="utf-8").splitlines()
    e = json.loads(lines[4])
    e["input_data"] = {"i": 99999}
    if "i" in e:
        e["i"] = 99999
    for k in list(e):
        if k not in ("input_data", "timestamp", "current_hash", "prev_hash",
                     "entry_id", "input_hash", "output_hash", "operation", "operator"):
            e[k] = "TAMPERED"
    lines[4] = json.dumps(e, ensure_ascii=False)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # 新实例（无缓存）必须报篡改
    fresh = _chain(tmp_path)
    r = fresh.verify()
    assert r["ok"] is False, "篡改历史行后必须校验失败"
    assert r.get("tampered_line") == 5 or r.get("breaks"), \
        f"应定位到第 5 行篡改，实际 {r}"


def test_incremental_is_faster(tmp_path):
    """增量必须真的更快，否则这个优化没意义。"""
    a = _chain(tmp_path)
    _fill(a, 400)
    t0 = time.perf_counter()
    a.verify()
    cold = time.perf_counter() - t0

    _fill(a, 5, "tail")
    t1 = time.perf_counter()
    a.verify()
    inc = time.perf_counter() - t1

    assert inc < cold * 0.5, f"增量({inc*1000:.1f}ms) 应显著快于全量({cold*1000:.1f}ms)"


def test_cache_hit_is_instant(tmp_path):
    """链未变化时直接命中缓存。"""
    a = _chain(tmp_path)
    _fill(a, 100)
    a.verify()
    t = time.perf_counter()
    a.verify()
    assert (time.perf_counter() - t) < 0.05


def test_truncated_chain_falls_back_to_full(tmp_path):
    """链变短（异常情况）时不能用旧前缀，必须全量重算。"""
    a = _chain(tmp_path)
    _fill(a, 30)
    a.verify()
    p = a.chain_path
    lines = p.read_text(encoding="utf-8").splitlines()
    p.write_text("\n".join(lines[:10]) + "\n", encoding="utf-8")
    r = a.verify()
    assert r["entries"] == 10, f"截断后应重算为 10 条，实际 {r['entries']}"
