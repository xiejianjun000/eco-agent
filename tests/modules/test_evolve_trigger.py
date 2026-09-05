"""L4 Evolve 自动触发钩子测试

现状缺口（README 自标）：无任务完成钩子、无每日调度接线。
目标：L2 mission 结束沉淀 (expectation, output, verdict) 三元组 →
      满足条件自动触发 Evolve；默认关闭（ECO_AUTO_EVOLVE=1 显式开启）。
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
from agent_core.commander_v2 import CommanderV2
from agent_core.evolve_trigger import EvolveTrigger


def _summary(completed=5, failed=0):
    return {
        "total_tasks": completed + failed,
        "completed": completed,
        "failed": failed,
        "verified": completed,
        "mission_replans": 0,
    }


def _tasks(n=2, with_triples=True):
    from agent_core.commander_v2 import Task, TaskStatus

    out = []
    for i in range(n):
        t = Task(description=f"任务{i}", expectation=f"判据{i}", status=TaskStatus.COMPLETED)
        t.output = f"产出{i}"
        t.verdict = f"结论{i}"
        out.append(t)
    return out


class TestExperienceRecording:
    def test_mission_recorded_as_jsonl_with_triples(self, tmp_path):
        """mission 结束必须沉淀三元组到经验库（Evolve 的原料）"""
        trig = EvolveTrigger(state_dir=tmp_path, evolve_runner=lambda h: {"ok": True})
        trig.record_mission(_summary(), _tasks(2))
        lines = (tmp_path / "experience.jsonl").read_text().strip().splitlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["summary"]["completed"] == 5
        assert entry["tasks"][0]["expectation"] == "判据0"
        assert entry["tasks"][0]["verdict"] == "结论0"
        assert entry["tasks"][0]["output"] == "产出0"

    def test_multiple_missions_accumulate(self, tmp_path):
        trig = EvolveTrigger(state_dir=tmp_path, evolve_runner=lambda h: {"ok": True}, threshold=100)
        for _ in range(3):
            trig.record_mission(_summary(), _tasks(1))
        assert len((tmp_path / "experience.jsonl").read_text().strip().splitlines()) == 3


class TestTriggerConditions:
    def test_threshold_not_reached_no_trigger(self, tmp_path):
        calls = []
        trig = EvolveTrigger(state_dir=tmp_path, threshold=5, evolve_runner=lambda h: calls.append(h) or {"ok": True})
        for _ in range(4):
            trig.record_mission(_summary(), _tasks(1))
            assert trig.maybe_trigger() is None
        assert calls == []

    def test_threshold_reached_triggers_with_history(self, tmp_path):
        """第 5 次 mission 触发，Evolve 收到全部经验历史"""
        calls = []
        trig = EvolveTrigger(state_dir=tmp_path, threshold=5, evolve_runner=lambda h: calls.append(h) or {"ok": True})
        for _ in range(5):
            trig.record_mission(_summary(), _tasks(1))
        assert trig.maybe_trigger() is not None
        assert len(calls) == 1 and len(calls[0]) == 5

    def test_failures_halve_threshold(self, tmp_path):
        """含失败任务的 mission 更有进化价值：阈值减半提前触发"""
        calls = []
        trig = EvolveTrigger(state_dir=tmp_path, threshold=6, evolve_runner=lambda h: calls.append(h) or {"ok": True})
        for _ in range(3):  # 3 条带失败的经验 = 6 等效 → 触发
            trig.record_mission(_summary(completed=3, failed=2), _tasks(1))
        assert trig.maybe_trigger() is not None
        assert len(calls) == 1

    def test_cooldown_prevents_immediate_retrigger(self, tmp_path):
        """触发后冷却期内不得重复触发"""
        calls = []
        trig = EvolveTrigger(
            state_dir=tmp_path, threshold=2, cooldown_s=3600, evolve_runner=lambda h: calls.append(h) or {"ok": True}
        )
        for _ in range(2):
            trig.record_mission(_summary(), _tasks(1))
        assert trig.maybe_trigger() is not None
        for _ in range(2):
            trig.record_mission(_summary(), _tasks(1))
        assert trig.maybe_trigger() is None, "冷却期内重复触发"
        assert len(calls) == 1

    def test_daily_schedule(self, tmp_path):
        """每日调度：距上次进化 >24h 应触发每日检查"""
        trig = EvolveTrigger(state_dir=tmp_path, threshold=100, evolve_runner=lambda h: {"ok": True})
        assert trig.should_evolve_daily() is True, "从未进化过应需要每日进化"
        trig._stamp_last_run(time.time() - 25 * 3600)
        assert trig.should_evolve_daily() is True
        trig._stamp_last_run(time.time() - 3600)
        assert trig.should_evolve_daily() is False


class TestCommanderWiring:
    def test_default_off_no_recording(self, monkeypatch, tmp_path):
        """默认（无环境变量）mission 结束不沉淀不触发（方案A一致性）"""
        monkeypatch.delenv("ECO_AUTO_EVOLVE", raising=False)
        monkeypatch.setenv("ECO_EVOLVE_STATE_DIR", str(tmp_path))
        cmd = CommanderV2()
        cmd.execute("默认关闭测试")
        assert not (tmp_path / "experience.jsonl").exists()

    def test_env_on_records_mission(self, monkeypatch, tmp_path):
        """ECO_AUTO_EVOLVE=1 时 mission 三元组自动沉淀"""
        monkeypatch.setenv("ECO_AUTO_EVOLVE", "1")
        monkeypatch.setenv("ECO_EVOLVE_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("ECO_EVOLVE_THRESHOLD", "100")  # 只沉淀不触发
        cmd = CommanderV2()
        cmd.execute("环境开启沉淀测试")
        lines = (tmp_path / "experience.jsonl").read_text().strip().splitlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["tasks"], "沉淀必须含任务三元组"
