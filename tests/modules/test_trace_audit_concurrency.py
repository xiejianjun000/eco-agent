"""审计链并发写入回归测试。

背景：线上 2026-09-01 23:27:03 出现 3 处哈希链断裂，定位为 _append 的
「读链尾 → 算哈希 → 追加」读改写竞态——两个会话（round3 与 round1）
在 6ms 内交错写入，都以同一条记录作 prev_hash，链条分叉。

修复：进程内 threading.Lock + 进程间 fcntl.flock 双重串行化。
本测试锁定该行为，防止回归。
"""
import json
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from agent_core.trace_audit import TraceAudit  # noqa: E402


def test_thread_concurrent_append_keeps_chain_intact():
    """8 线程各写 10 条：修复前第 2 行即断裂。"""
    with tempfile.TemporaryDirectory() as d:
        audit = TraceAudit(base_dir=Path(d))

        def w(i):
            for k in range(10):
                audit.record_tool_call(f"t{i}", {"k": k}, "ok", 1)

        ts = [threading.Thread(target=w, args=(i,)) for i in range(8)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()

        r = audit.verify()
        assert r["ok"] is True, r
        assert r["entries"] == 80
        assert r["breaks"] == []


def test_process_concurrent_append_keeps_chain_intact():
    """4 进程各写 10 条：仅有线程锁时仍会断裂，需要 flock。"""
    with tempfile.TemporaryDirectory() as d:
        script = (
            f"import sys; sys.path.insert(0, {str(REPO)!r})\n"
            "from pathlib import Path\n"
            "from agent_core.trace_audit import TraceAudit\n"
            f"a = TraceAudit(base_dir=Path({d!r}))\n"
            "for k in range(10): a.record_tool_call('p', {'k': k}, 'ok', 1)\n"
        )
        procs = [subprocess.Popen([sys.executable, "-c", script]) for _ in range(4)]
        for p in procs:
            assert p.wait(timeout=120) == 0

        r = TraceAudit(base_dir=Path(d)).verify()
        assert r["ok"] is True, r
        assert r["entries"] == 40
        assert r["breaks"] == []


def test_verify_reports_breaks_without_early_return():
    """人为制造断裂：verify 必须继续校验后续内容，而非早退。

    这是本次修复的另一半——早退会让断点之后的记录全部失去验证能力
    （线上曾因此使 1834 条记录无法校验）。
    """
    with tempfile.TemporaryDirectory() as d:
        audit = TraceAudit(base_dir=Path(d))
        for k in range(5):
            audit.record_tool_call("t", {"k": k}, "ok", 1)

        # 造一个「真实形态」的并发分叉：删掉第 3 行。
        # 于是第 4 行的 prev_hash 指向已不存在的第 3 行 —— 接续断了，
        # 但每行自身的 current_hash 仍与其 prev_hash 自洽（真并发断裂就是这样，
        # 不能用改 prev_hash 来模拟：那会连带 current_hash 失配，
        # 被正确判定成「内容篡改」，性质完全不同）。
        lines = audit.chain_path.read_text(encoding="utf-8").splitlines()
        del lines[2]
        audit.chain_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        r = audit.verify()
        assert r["ok"] is False
        assert len(r["breaks"]) == 1
        assert r["breaks"][0]["line"] == 3   # 原第 4 行，删除后成为第 3 行
        # 关键：剩余 4 条全部完成内容重算，没有因断点早退
        assert r["entries"] == 4
        assert r["segments"] == 2
        assert "tampered_line" not in r  # 只是断链，不是篡改


def test_content_tampering_is_hard_failure():
    """内容被改必须硬失败——与链接断裂性质不同，不能降级为告警。"""
    with tempfile.TemporaryDirectory() as d:
        audit = TraceAudit(base_dir=Path(d))
        for k in range(4):
            audit.record_tool_call("t", {"k": k}, "ok", 1)

        lines = audit.chain_path.read_text(encoding="utf-8").splitlines()
        e = json.loads(lines[1])
        e["result"] = "已被篡改的结果"
        lines[1] = json.dumps(e, ensure_ascii=False)
        audit.chain_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        r = audit.verify()
        assert r["ok"] is False
        assert r["tampered_line"] == 2
