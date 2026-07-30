#!/usr/bin/env python3
"""EcoBench-mini 测试：数据集完整性 / 评分诚实性 / mock 流程"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmarks.ecobench.run_ecobench import score_item, load_dataset, MOCK_ANSWER, main

ECOBENCH_DIR = Path(__file__).resolve().parents[2] / "benchmarks" / "ecobench"


class TestDataset:
    def test_50_questions_complete(self):
        items = load_dataset()
        assert len(items) == 50
        cats = {}
        for it in items:
            assert it["question"] and it["golden_answer"]
            assert it["required_citations"] and it["key_points"]
            cats[it["category"]] = cats.get(it["category"], 0) + 1
        # 五大类每类 10 题
        assert len(cats) == 5
        assert all(v == 10 for v in cats.values())


class TestScoringHonesty:
    def _item(self):
        return load_dataset()[0]

    def test_golden_answer_scores_high(self):
        it = self._item()
        sc = score_item(it["golden_answer"], it)
        assert sc["citation_hit"] == 1.0
        assert sc["keypoint_f1"] == 1.0

    def test_totally_wrong_answer_scores_zero(self):
        """构造全错答案必须低分——评分不得保底"""
        it = self._item()
        sc = score_item("答非所问：今天天气很好，与法律无关。", it)
        assert sc["citation_hit"] == 0.0
        assert sc["keypoint_f1"] == 0.0

    def test_partial_answer_proportional(self):
        it = self._item()
        # 只含一个 citation 无要点 → 部分分
        sc = score_item(f"依据{it['required_citations'][0]}处理。", it)
        assert 0 < sc["citation_hit"] <= 1.0
        assert sc["keypoint_f1"] < 1.0

    def test_mock_answer_low_score(self):
        it = self._item()
        sc = score_item(MOCK_ANSWER, it)
        assert sc["citation_hit"] == 0.0
        assert sc["keypoint_f1"] == 0.0


class TestMockRun:
    def test_mock_pipeline(self, tmp_path, monkeypatch):
        out = tmp_path / "report.json"
        monkeypatch.setenv("ECO_LLM_DISABLE", "1")
        rc = main(["--mock", "--limit", "5", "--out", str(out)])
        assert rc == 0
        rep = json.loads(out.read_text(encoding="utf-8"))
        assert rep["summary"]["mode"] == "mock"
        assert rep["summary"]["n_questions"] == 5
        # mock 答案无实质内容，分数必须低（诚实性）
        assert rep["summary"]["citation_accuracy"] == 0.0
        assert rep["summary"]["keypoint_f1"] < 0.3
