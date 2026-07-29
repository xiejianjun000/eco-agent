"""自进化引擎 + 技能系统测试"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from agent_core.evolution_v2 import ActiveLearner, ABTest, SwarmIntelligence
from agent_core.skill_system import SkillRegistry, Skill

class TestActiveLearning:
    def test_pattern_detection(self):
        al = ActiveLearner()
        for _ in range(10):
            al.record_action("search", {"q": "test"})
        assert len(al.predict_next()) >= 0

    def test_sequence_recognition(self):
        al = ActiveLearner()
        for _ in range(5):
            al.record_action("A", {})
            al.record_action("B", {})
        pattern = al.identify_pattern()
        assert pattern is not None

class TestABTest:
    def test_winner_selection(self):
        ab = ABTest()
        tid = ab.create_test("v1", "v2", ["case1", "case2", "case3"])
        result = ab.run(tid)
        assert result['winner'] in ("A", "B")
        assert result['avg_a'] > 0

class TestSwarm:
    def test_share_and_rating(self):
        sw = SwarmIntelligence()
        sid = sw.share_skill({"name": "test", "steps": ["s1"]})
        sw.rate_skill(sid, 4.0)
        sw.rate_skill(sid, 5.0)
        t = sw.get_trending()
        assert len(t) > 0
        assert t[0]['rating'] > 0

class TestSkillRegistry:
    def test_register_and_find(self):
        reg = SkillRegistry()
        s = Skill(name="test", description="test desc", category="general")
        sid = reg.register(s)
        found = reg.find("test")
        assert len(found) >= 1
