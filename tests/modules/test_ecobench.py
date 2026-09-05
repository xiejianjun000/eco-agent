#!/usr/bin/env python3
"""EcoBench-mini 测试：数据集完整性 / 评分诚实性 / mock 流程"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmarks.ecobench.run_ecobench import MOCK_ANSWER, load_dataset, main, score_item

ECOBENCH_DIR = Path(__file__).resolve().parents[2] / "benchmarks" / "ecobench"


class TestDataset:
    def test_70_questions_complete(self):
        items = load_dataset()
        assert len(items) == 70
        cats = {}
        for it in items:
            assert it["question"] and it["golden_answer"]
            assert it["required_citations"] and it["key_points"]
            cats[it["category"]] = cats.get(it["category"], 0) + 1
        # 原五大类每类 10 题 + 法典专题四类每类 5 题
        assert len(cats) == 9
        for c in ("法条引用", "违法认定", "处罚裁量", "执法程序", "法典新旧衔接"):
            assert cats[c] == 10
        for c in ("法典-继承映射", "法典-新旧衔接", "法典-框架结构", "法典-引用规范"):
            assert cats[c] == 5

    def test_codex_questions_golden_nonempty(self):
        """法典专题（EB51-EB70）金标准必须非空且含法典定位信息，严禁空泛"""
        items = {it["id"]: it for it in load_dataset()}
        for i in range(51, 71):
            it = items[f"EB{i:02d}"]
            assert it["category"].startswith("法典-")
            assert len(it["golden_answer"]) >= 50
            assert it["source"].startswith("EHS知识库")
            # 金标准必须自洽：所有必引项在金标准中真实出现（评分器同口径归一化）
            from benchmarks.ecobench.run_ecobench import _norm

            ga = _norm(it["golden_answer"])
            for c in it["required_citations"]:
                assert _norm(c) in ga, f"{it['id']} 必引项 {c} 未在金标准中出现"
            # 引用法典条款号的题，golden 必须含同一条款号（防编造）
            for c in it["required_citations"]:
                m = re.search(r"第[零一二三四五六七八九十百千两\d]+条", c)
                if m and "生态环境法典" in c:
                    assert m.group(0) in it["golden_answer"]

    def test_transition_notes_on_repealed_laws(self):
        """引用已被法典废止单行法的旧题应标注过渡适用"""
        items = load_dataset()
        noted = [it for it in items if "note" in it]
        assert noted, "应有过渡适用标注"
        for it in noted:
            assert "过渡适用" in it["note"] and "2026-08-15" in it["note"]


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
