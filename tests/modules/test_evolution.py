"""自进化引擎 + 技能系统测试——确定性数据内容断言"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
import pytest
import agent_core.evolution_v2 as evo
from agent_core.evolution_v2 import ActiveLearner, ABTest, SwarmIntelligence
from agent_core.skill_system import SkillRegistry, Skill


@pytest.fixture
def learner(tmp_path, monkeypatch):
    """隔离持久化目录，避免测试间状态污染"""
    monkeypatch.setattr(evo, "DATA_DIR", tmp_path)
    return ActiveLearner()


class TestActiveLearning:
    def test_prediction_content(self, learner):
        """10 次同类操作后，预测首位必须是该类型且置信度=1.0"""
        for _ in range(10):
            learner.record_action("search", {"q": "test"})
        preds = learner.predict_next()
        assert len(preds) == 1
        assert preds[0]["predicted_type"] == "search"
        assert preds[0]["confidence"] == 1.0

    def test_no_prediction_below_threshold(self, tmp_path, monkeypatch):
        monkeypatch.setattr(evo, "DATA_DIR", tmp_path)
        al = ActiveLearner()
        al.record_action("A", {})
        al.record_action("B", {})
        assert al.predict_next() == [], "不足3条记录不得产生预测"

    def test_sequence_recognition_exact(self, learner):
        """A,B 交替 5 轮 → 必须识别出高频三元序列 (A,B,A)，频次 4"""
        for _ in range(5):
            learner.record_action("A", {})
            learner.record_action("B", {})
        pattern = learner.identify_pattern()
        assert pattern is not None
        assert pattern["sequence"] == ["A", "B", "A"]
        assert pattern["frequency"] == 4


class TestABTest:
    def test_deterministic_winner(self):
        """确定性 scorer：同输入两次运行结果必须完全一致（可复现）"""
        def scorer(skill, case):
            return 0.9 if "精准" in skill else 0.3
        ab1, ab2 = ABTest(scorer=scorer), ABTest(scorer=scorer)
        tid1 = ab1.create_test("精准检索技能", "粗略检索技能", ["case1", "case2"])
        tid2 = ab2.create_test("精准检索技能", "粗略检索技能", ["case1", "case2"])
        r1, r2 = ab1.run(tid1), ab2.run(tid2)
        assert r1["winner"] == "A"
        assert r1["avg_a"] == 0.9 and r1["avg_b"] == 0.3
        assert (r1["avg_a"], r1["avg_b"]) == (r2["avg_a"], r2["avg_b"]), "A/B 评测必须可复现"

    def test_unknown_test_id(self):
        assert ABTest().run("ab_不存在")["error"] == "测试不存在"


class TestSwarm:
    def test_share_rating_anonymization(self):
        sw = SwarmIntelligence()
        sid = sw.share_skill({"name": "test", "steps": ["s1"], "author": "user_secret"})
        sw.rate_skill(sid, 4.0)
        sw.rate_skill(sid, 5.0)
        t = sw.get_trending()
        assert len(t) == 1
        assert t[0]["rating"] == 4.5, "评分必须是两次评分的均值"
        assert "author" not in t[0], "共享必须匿名化移除作者信息"
        assert t[0]["downloads"] == 2

    def test_rating_clamped(self):
        sw = SwarmIntelligence()
        sid = sw.share_skill({"name": "x"})
        sw.rate_skill(sid, 99.0)
        assert sw.get_trending()[0]["rating"] == 5.0, "评分必须截断到 0~5"


class TestSkillRegistry:
    def test_register_and_find(self, tmp_path, monkeypatch):
        import agent_core.skill_system as ss
        monkeypatch.setattr(ss, "DATA_DIR", tmp_path)
        monkeypatch.setattr(ss, "SKILL_DIR", tmp_path / "skills")  # 防止向仓库 skills/ 写运行时产物
        reg = SkillRegistry()
        s = Skill(name="法规精准检索", description="按条文号精确检索法规", category="gov")
        sid = reg.register(s)
        found = reg.find("精准检索")
        assert len(found) == 1
        assert found[0].id == sid
        assert found[0].name == "法规精准检索"
        assert reg.find("完全不相关的词") == []
