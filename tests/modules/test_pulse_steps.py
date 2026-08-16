"""L3 Pulse 五步骤真实化测试

占位 → 真实：每步必须有可观测的真实副作用/真实数据，不再返回常量。
离线约束：全部在 tmp_path 下构造，不触碰真实 vault / ~/.eco。
"""
import sys
import os
import json
import sqlite3
import time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from agent_core.heartbeat import PulseSteps


def _make_env(tmp_path):
    """构造受控环境：vault（3 md）+ 记忆目录 + 状态文件 + 小 SQLite"""
    vault = tmp_path / "vault"
    (vault / "raw").mkdir(parents=True)
    for i in range(3):
        (vault / "raw" / f"法规{i}.md").write_text(f"# 法规{i}\n第{i+1}条 内容", encoding="utf-8")
    mem = tmp_path / "memory"
    mem.mkdir()
    (mem / "notes.md").write_text("# 笔记", encoding="utf-8")
    state = tmp_path / "pulse_state.json"
    db = tmp_path / "vectors.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE t (id TEXT)")
    conn.executemany("INSERT INTO t VALUES (?)", [(f"d{i}",) for i in range(10)])
    conn.commit(); conn.close()
    return PulseSteps(vault_path=vault, watch_dirs=[vault, mem],
                      state_file=state, db_paths=[db], stale_days=90)


class TestStepSync:
    def test_sync_reports_real_counts(self, tmp_path):
        """同步必须返回真实文件数/字节数，不是 'sync_ok' 常量"""
        steps = _make_env(tmp_path)
        r = steps.step_sync()
        assert r["files"] == 4, f"必须数出 4 个文件: {r}"
        assert r["bytes"] > 0
        assert r["stores"] == 2

    def test_sync_persists_snapshot(self, tmp_path):
        """同步必须落盘快照（差异检测的基线）"""
        steps = _make_env(tmp_path)
        steps.step_sync()
        assert steps._state_file.exists()
        snap = json.loads(steps._state_file.read_text())
        assert len(snap["files"]) == 4


class TestStepDiff:
    def test_no_changes_after_sync(self, tmp_path):
        """刚同步完 → 无差异"""
        steps = _make_env(tmp_path)
        steps.step_sync()
        r = steps.step_diff()
        assert r["changed"] == 0

    def test_detects_new_and_modified(self, tmp_path):
        """新增 1 个 + 修改 1 个 → 差异数 2，且能说出谁变了"""
        steps = _make_env(tmp_path)
        steps.step_sync()
        vault = tmp_path / "vault"
        (vault / "raw" / "新法规.md").write_text("# 新规", encoding="utf-8")
        time.sleep(0.02)
        f0 = vault / "raw" / "法规0.md"
        f0.write_text("# 法规0 修订版 更长的内容", encoding="utf-8")
        os.utime(f0, (time.time() + 1, time.time() + 1))
        r = steps.step_diff()
        assert r["changed"] == 2, f"必须检出 2 处差异: {r}"
        assert any("新法规" in p for p in r["files"])


class TestStepRuleEngine:
    def test_stale_knowledge_rule_triggers(self, tmp_path):
        """超期未更新文件必须触发知识保鲜规则（D10 抓手），新鲜文件不触发"""
        steps = _make_env(tmp_path)
        old = tmp_path / "vault" / "raw" / "法规1.md"
        old_ts = time.time() - 100 * 86400
        os.utime(old, (old_ts, old_ts))
        r = steps.step_rule_engine()
        assert r["triggered"], "过期知识未触发规则"
        assert any("法规1" in t for t in r["triggered"])
        assert not any("法规2" in t for t in r["triggered"])

    def test_all_fresh_no_trigger(self, tmp_path):
        steps = _make_env(tmp_path)
        r = steps.step_rule_engine()
        assert r["triggered"] == []


class TestStepMemCron:
    def test_vacuum_real_sqlite(self, tmp_path):
        """内存整理必须真实 VACUUM + 完整性检查，不是 'mem_ok' 常量"""
        steps = _make_env(tmp_path)
        r = steps.step_mem_cron()
        assert r["integrity"] == "ok"
        assert r["vacuumed"] == 1

    def test_missing_db_graceful(self, tmp_path):
        """DB 不存在 → 跳过不崩"""
        steps = PulseSteps(vault_path=tmp_path, watch_dirs=[tmp_path],
                           state_file=tmp_path / "s.json",
                           db_paths=[tmp_path / "nonexistent.db"])
        r = steps.step_mem_cron()
        assert r["vacuumed"] == 0


class TestStepSuggestions:
    def test_stale_knowledge_generates_suggestion(self, tmp_path):
        """有过期知识 → 必须产出含数量的建议文本"""
        steps = _make_env(tmp_path)
        r = steps.step_suggestions({"stale_count": 3, "changed": 0})
        assert r and any("3" in s for s in r), f"建议必须含过期数量: {r}"

    def test_nothing_noteworthy_returns_none(self, tmp_path):
        """一切正常 → None（静默原则：不打扰用户）"""
        steps = _make_env(tmp_path)
        assert steps.step_suggestions({"stale_count": 0, "changed": 0}) is None


class TestStepVerify:
    """STEP 6: 运维体检集成测试"""

    def test_verify_silent_when_clean(self, tmp_path, monkeypatch):
        """无异常时静默返回 None（体检不干扰心跳）"""
        from agent_core.heartbeat import PulseSteps
        steps = PulseSteps(state_file=tmp_path / "state.json")

        import _scripts.verify_ops as vo
        monkeypatch.setattr(vo, "run_checks", lambda: {
            "session_logs": {"all_verified": True, "truncated_total": 0},
            "evolution_report": {"exists": False, "pass": False},
            "memory_conflicts": {"open_conflicts": 0},
        })
        assert steps.step_verify() is None

    def test_verify_reports_issues(self, tmp_path, monkeypatch):
        """发现异常时返回问题清单，供 suggestions 汇总"""
        from agent_core.heartbeat import PulseSteps
        steps = PulseSteps(state_file=tmp_path / "state.json")

        import _scripts.verify_ops as vo
        monkeypatch.setattr(vo, "run_checks", lambda: {
            "session_logs": {"all_verified": False, "truncated_total": 2},
            "evolution_report": {"exists": True, "chars": 100, "pass": False},
            "memory_conflicts": {"open_conflicts": 3},
        })
        issues = steps.step_verify()
        assert issues is not None
        assert any("日志校验异常" in i for i in issues)
        assert any("进化报告篇幅不足" in i for i in issues)
        assert any("3 条记忆矛盾" in i for i in issues)

    def test_verify_failure_does_not_raise(self, tmp_path, monkeypatch):
        """体检执行失败不得击穿心跳（降级为单条提示）"""
        from agent_core.heartbeat import PulseSteps
        steps = PulseSteps(state_file=tmp_path / "state.json")

        import _scripts.verify_ops as vo
        monkeypatch.setattr(vo, "run_checks", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        issues = steps.step_verify()
        assert issues is not None and any("不可用" in i for i in issues)

    def test_suggestions_include_verify_issues(self, tmp_path):
        from agent_core.heartbeat import PulseSteps
        steps = PulseSteps(state_file=tmp_path / "state.json")
        sug = steps.step_suggestions({"verify_issues": ["问题A", "问题B", "问题C", "问题D"]})
        assert sug is not None
        assert sum(1 for s in sug if "[运维体检]" in s) == 3  # 最多带 3 条
