"""长时运行实证剧本（benchmarks/longrun_pulse_evolve.py）测试

短时/合成事件验证剧本的日志记录与报告生成功能，不跑真实长时运行、
不触发真实 MetaEvolution（避免向 memory-tree 写运行时产物）。
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from benchmarks.longrun_pulse_evolve import CLAIM_VS_OBSERVED, LongRunObserver


def _read_events(jsonl_path):
    return [json.loads(line) for line in Path(jsonl_path).read_text(encoding="utf-8").splitlines() if line.strip()]


class TestShortPulseRun:
    def test_short_run_produces_jsonl_and_report(self, tmp_path):
        """3.5s 短跑（心跳 1s）：JSONL 必须有心跳事件，报告必须含各观测章节"""
        obs = LongRunObserver(duration_s=3.5, smoke=True, reports_dir=tmp_path, pulse_interval_s=1, enable_evolve=False)
        out = obs.run()

        events = _read_events(out["jsonl"])
        types = {e["type"] for e in events}
        assert "run_start" in types and "run_end" in types

        heartbeats = [e for e in events if e["type"] == "heartbeat"]
        assert len(heartbeats) >= 2, f"3.5s/1s间隔 应至少 2 次心跳，实际 {len(heartbeats)}"
        for hb in heartbeats:
            assert set(hb["steps"]) == {"sync", "diff", "rule_engine", "mem_cron", "suggestions"}
            assert hb["steps"]["sync"]["status"] == "ok"
            assert "interval_s" in hb

        # 关闭进化时不得出现进化事件
        assert "evolve_cycle" not in types

        report = Path(out["report"]).read_text(encoding="utf-8")
        assert "L3 Pulse 心跳观测" in report
        assert "自适应降频行为" in report
        assert "README 声称 vs 实测对照" in report
        assert "异常清单" in report
        assert "无异常" in report

    def test_run_start_records_claim_table_and_llm_flag(self, tmp_path):
        """run_start 事件必须带声称/实测对照表与 LLM 降级标记"""
        obs = LongRunObserver(duration_s=1.2, smoke=True, reports_dir=tmp_path, pulse_interval_s=1, enable_evolve=False)
        out = obs.run()
        run_start = next(e for e in _read_events(out["jsonl"]) if e["type"] == "run_start")
        assert run_start["llm_disabled"] is True, "conftest 强制 ECO_LLM_DISABLE=1"
        assert len(run_start["claim_vs_observed"]) == len(CLAIM_VS_OBSERVED)
        claims = [c["claim"] for c in run_start["claim_vs_observed"]]
        assert any("电池" in c for c in claims), "电池降频差异必须入档"


class TestReportGeneration:
    def _observer(self, tmp_path):
        return LongRunObserver(duration_s=1, smoke=True, reports_dir=tmp_path, enable_evolve=False)

    def test_report_with_synthetic_evolve_and_anomaly(self, tmp_path):
        """合成 evolve_cycle/anomaly 事件：报告必须呈现进化产物与异常清单"""
        obs = self._observer(tmp_path)
        obs._emit({"type": "run_start", "llm_disabled": True, "pulse_interval_s": 2, "pulse_adaptive_bounds": [1, 4]})
        obs._emit(
            {
                "type": "evolve_cycle",
                "trigger": "script_manual（测试）",
                "elapsed_ms": 12.3,
                "version": 7,
                "phases": {
                    "experience_replay": {"total_replayed": 0, "success_count": 0, "fail_count": 0, "success_rate": "0%"},
                    "gap_analysis": {"gaps": [], "gap_count": 0},
                    "skill_gen": {"generated": 0, "optimized": 0},
                    "reflector": {"accept": 0, "reject": 0, "llm_critique": None},
                    "curator_gate": "pass",
                    "memory_consolidation": {"working_to_episodic": "consolidated"},
                    "self_versioning": {"version": 7, "snapshot_path": "/x/v7", "retained_versions": 3},
                },
                "llm_disabled": True,
                "artifacts": {
                    "report_path": "/x/evolution_report_v7.md",
                    "report_exists": True,
                    "version_snapshot": "/x/v7",
                    "version_snapshot_exists": True,
                    "skill_files_generated": "无",
                    "memory_consolidation_files": "无",
                },
            }
        )
        obs._emit({"type": "anomaly", "source": "pulse.sync", "error": "boom"})
        path = obs.generate_report("sigint")
        text = Path(path).read_text(encoding="utf-8")
        assert "五阶段产物清单" in text
        assert "v7" in text and "script_manual" in text
        assert "boom" in text and "pulse.sync" in text
        assert "结束原因：sigint" in text

    def test_heartbeat_gap_stats_in_report(self, tmp_path):
        """合成两次心跳：报告必须给出间隔 min/avg/max 行"""
        obs = self._observer(tmp_path)
        obs._emit({"type": "run_start", "llm_disabled": True, "pulse_interval_s": 2, "pulse_adaptive_bounds": [1, 4]})
        step = {"status": "ok", "result": "sync_ok"}
        for i, ts in enumerate(["2026-07-31T10:00:00", "2026-07-31T10:00:10"], 1):
            obs._emit(
                {
                    "type": "heartbeat",
                    "pulse_id": f"pulse_{i}",
                    "count": i,
                    "timestamp": ts,
                    "elapsed_s": 0.01,
                    "interval_s": 2,
                    "interval_adapted_from": None,
                    "steps": {n: step for n in LongRunObserver.PULSE_STEPS},
                }
            )
        text = Path(obs.generate_report("deadline")).read_text(encoding="utf-8")
        assert "10.0s / 10.0s / 10.0s" in text
        assert "未观察到间隔自适应调整" in text
