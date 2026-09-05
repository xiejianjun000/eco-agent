"""test_eval_runner.py - evals/runner.py 打分/门控/baseline 对比单测（全 mock，不调真实 LLM）"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from evals import runner  # noqa: E402


class MockLLM:
    """按 question 关键字返回预设答案的 mock client（与 LLMClient.complete 接口一致）"""

    def __init__(self, mapping=None, default="", fail_ids=None):
        self.mapping = mapping or {}
        self.default = default
        self.calls = []

    def complete(self, prompt, system="", max_tokens=512):
        self.calls.append(prompt)
        if "raise" in prompt:
            raise RuntimeError("mock boom")
        for k, v in self.mapping.items():
            if k in prompt:
                return v
        return self.default


def _write_dataset(tmp_path, records):
    p = tmp_path / "ds.jsonl"
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records), encoding="utf-8")
    return p


SAMPLES = [
    {"id": "T-001", "category": "法规依据", "question": "q1", "expected_points": ["第四十五条", "罚款"]},
    {"id": "T-002", "category": "裁量计算", "question": "q2", "expected_points": ["60万", "按日连续处罚"]},
    {"id": "T-003", "category": "注入抗性", "question": "raise q3", "expected_points": ["拒绝"]},
]


class TestGate:
    def test_eval_enabled_default_off(self, monkeypatch):
        monkeypatch.delenv("ECO_EVAL", raising=False)
        assert runner.eval_enabled() is False

    def test_eval_enabled_on(self, monkeypatch):
        monkeypatch.setenv("ECO_EVAL", "1")
        assert runner.eval_enabled() is True

    def test_main_skips_without_gate(self, monkeypatch, capsys):
        monkeypatch.delenv("ECO_EVAL", raising=False)
        rc = runner.main([])
        assert rc == 0
        assert "ECO_EVAL" in capsys.readouterr().out


class TestLoadDataset:
    def test_load_builtin_dataset(self):
        samples = runner.load_dataset(runner.DEFAULT_DATASET)
        assert len(samples) >= 40
        cats = {s["category"] for s in samples}
        assert cats == runner.VALID_CATEGORIES

    def test_load_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            runner.load_dataset(tmp_path / "nope.jsonl")

    def test_load_missing_field(self, tmp_path):
        p = _write_dataset(tmp_path, [{"id": "X", "category": "法规依据", "question": "q"}])
        with pytest.raises(ValueError):
            runner.load_dataset(p)

    def test_load_bad_category(self, tmp_path):
        p = _write_dataset(tmp_path, [{"id": "X", "category": "不存在的类目", "question": "q", "expected_points": ["a"]}])
        with pytest.raises(ValueError):
            runner.load_dataset(p)


class TestScoring:
    def test_full_hit(self):
        sc = runner.score_answer("依据第四十五条，处罚款", ["第四十五条", "罚款"])
        assert sc["score"] == 1.0
        assert sc["misses"] == []

    def test_partial_hit(self):
        sc = runner.score_answer("只提到罚款", ["第四十五条", "罚款"])
        assert sc["score"] == 0.5
        assert sc["misses"] == ["第四十五条"]

    def test_empty_answer_zero(self):
        assert runner.score_answer("", ["a"])["score"] == 0.0

    def test_case_insensitive(self):
        assert runner.score_answer("Answer is ABC", ["abc"])["score"] == 1.0


class TestRunEval:
    def test_run_eval_mock(self):
        client = MockLLM(mapping={"q1": "依据第四十五条并处罚款", "q2": "按日连续处罚合计60万"})
        report = runner.run_eval(SAMPLES, client)
        assert report["total"] == 3
        assert len(client.calls) == 3
        assert report["category_avg"]["法规依据"] == 1.0
        # 第三条 mock 抛异常 → error 记录且 score 0，不中断整轮
        r3 = report["results"][2]
        assert r3["error"] is not None and r3["score"] == 0.0

    def test_report_json_serializable_and_written(self, tmp_path):
        client = MockLLM(default="拒绝")
        report = runner.run_eval(SAMPLES, client)
        out = runner.write_report(report, tmp_path / "sub" / "r.json")
        loaded = json.loads(out.read_text(encoding="utf-8"))
        assert loaded["total"] == 3
        assert "overall_score" in loaded and "category_avg" in loaded


class TestBaseline:
    CUR = {"overall_score": 0.8, "category_avg": {"法规依据": 0.9, "裁量计算": 0.7}}
    BASE = {"overall_score": 0.85, "category_avg": {"法规依据": 0.95, "裁量计算": 0.85}}

    def test_regression_detected(self):
        bc = runner.compare_baseline(self.CUR, self.BASE, threshold=0.05)
        assert bc["regressed"] is True
        assert "裁量计算" in bc["regressions"]
        assert bc["category_delta"]["裁量计算"] == pytest.approx(-0.15, abs=1e-4)

    def test_no_regression_within_threshold(self):
        cur = {"overall_score": 0.81, "category_avg": {"法规依据": 0.9, "裁量计算": 0.82}}
        bc = runner.compare_baseline(cur, self.BASE, threshold=0.05)
        assert bc["regressed"] is False
        assert bc["regressions"] == []

    def test_overall_regression_flag(self):
        cur = {"overall_score": 0.5, "category_avg": {"法规依据": 0.95, "裁量计算": 0.85}}
        bc = runner.compare_baseline(cur, self.BASE, threshold=0.05)
        assert "__overall__" in bc["regressions"]

    def test_main_baseline_missing_file(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ECO_EVAL", "1")
        ds = _write_dataset(tmp_path, SAMPLES[:1])
        rc = runner.main(["--dataset", str(ds), "--baseline", str(tmp_path / "absent.json")])
        assert rc == 2

    def test_main_with_mock_llm_and_baseline(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ECO_EVAL", "1")
        ds = _write_dataset(tmp_path, SAMPLES[:2])
        # 注入 mock LLMClient，避免真实 HTTP
        import agent_core.llm_client as lc

        monkeypatch.setattr(lc, "LLMClient", lambda: MockLLM(mapping={"q1": "第四十五条 罚款", "q2": "按日连续处罚"}))
        report_path = tmp_path / "r.json"
        rc1 = runner.main(["--dataset", str(ds), "--report", str(report_path)])
        assert rc1 == 0 and report_path.exists()
        # 基线（更高分）对比 → 回归 exit 1
        base = {"overall_score": 1.0, "category_avg": {"法规依据": 1.0, "裁量计算": 1.0}}
        bp = tmp_path / "base.json"
        bp.write_text(json.dumps(base, ensure_ascii=False), encoding="utf-8")
        rc2 = runner.main(
            ["--dataset", str(ds), "--report", str(tmp_path / "r2.json"), "--baseline", str(bp), "--threshold", "0.01"]
        )
        assert rc2 == 1
        r2 = json.loads((tmp_path / "r2.json").read_text(encoding="utf-8"))
        assert r2["baseline_compare"]["regressed"] is True
