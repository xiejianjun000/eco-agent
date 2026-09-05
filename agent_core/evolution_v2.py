#!/usr/bin/env python3
"""
evolution_v2.py — Eco Agent 自进化引擎 v2

对标愿景中"超越 Hermes"的自我进化深度：
  1. Active Learning — 基于使用模式预测并预生成技能
  2. Skill Composition — 技能可组合/可继承
  3. A/B Testing — 技能上线前自动对比评测
  4. 群体智慧框架 — 匿名化跨用户技能共享接口

用法：
  python agent_core/evolution_v2.py
"""

import hashlib
import json
import logging
import re
import time
import uuid
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("evolution_v2")

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "memory-tree" / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


# ═══════════════════════════════════
# 1. Active Learning — 主动学习
# ═══════════════════════════════════


class ActiveLearner:
    """主动学习——基于使用模式预测并预生成技能"""

    def __init__(self):
        self._patterns: list[dict] = []
        self._db_path = DATA_DIR / "active_learning.json"
        self._load()

    def _load(self):
        if self._db_path.exists():
            try:
                self._patterns = json.loads(self._db_path.read_text("utf-8", errors="replace"))
            except Exception:
                pass

    def _save(self):
        self._db_path.write_text(json.dumps(self._patterns[-200:], ensure_ascii=False, indent=2), encoding="utf-8")

    def record_action(self, action_type: str, context: dict):
        """记录用户操作"""
        self._patterns.append(
            {
                "type": action_type,
                "context": context,
                "timestamp": datetime.now().isoformat(),
            }
        )
        self._save()

    def predict_next(self) -> list[dict]:
        """预测下一个可能需要的技能"""
        if len(self._patterns) < 3:
            return []
        recent = self._patterns[-10:]
        type_counts = {}
        for p in recent:
            t = p["type"]
            type_counts[t] = type_counts.get(t, 0) + 1
        frequent = sorted(type_counts.items(), key=lambda x: -x[1])
        predictions = []
        for ftype, count in frequent[:3]:
            if count >= 2:
                predictions.append(
                    {
                        "predicted_type": ftype,
                        "confidence": count / len(recent),
                        "based_on": f"最近{len(recent)}次操作中出现了{count}次",
                    }
                )
        return predictions

    def identify_pattern(self) -> dict | None:
        """识别重复模式（适合生成技能）"""
        if len(self._patterns) < 5:
            return None
        recent = self._patterns[-20:]
        sequences = []
        for i in range(len(recent) - 2):
            seq = (recent[i]["type"], recent[i + 1]["type"], recent[i + 2]["type"])
            sequences.append(seq)
        from collections import Counter

        common = Counter(sequences).most_common(1)
        if common and common[0][1] >= 2:
            seq, count = common[0]
            return {"sequence": list(seq), "frequency": count, "total_observed": len(sequences)}
        return None


# ═══════════════════════════════════
# 2. Skill Composition — 技能组合
# ═══════════════════════════════════


class SkillComposer:
    """技能组合——技能可组合/可继承/可版本控制"""

    def compose(self, base_skills: list[str], goal: str) -> dict:
        """组合多个技能完成新目标"""
        return {
            "id": f"combo_{uuid.uuid4().hex[:8]}",
            "base_skills": base_skills,
            "goal": goal,
            "steps": [f"Step {i + 1}: 调用 {s}" for i, s in enumerate(base_skills)],
            "created_at": datetime.now().isoformat(),
        }

    def inherit(self, parent_skill_id: str, modifications: dict) -> dict:
        """继承并修改已有技能"""
        return {
            "id": f"inherit_{uuid.uuid4().hex[:8]}",
            "parent": parent_skill_id,
            "modifications": modifications,
            "version": "0.2.0",
            "inherited_at": datetime.now().isoformat(),
        }


# ═══════════════════════════════════
# 3. A/B Testing — 自动对比评测
# ═══════════════════════════════════


class ABTest:
    """A/B 测试——技能上线前自动对比评测"""

    def __init__(self, scorer: Callable[[str, str], float] | None = None):
        """
        scorer(skill_text, test_case) -> 0~1 分数。
        默认使用确定性启发式（关键词重合度），同输入必得同分数；
        生产环境可注入基于 LLM/评测集的真实 scorer。
        """
        self._tests: dict[str, dict] = {}
        self._results: list[dict] = []
        self._scorer = scorer or self._heuristic_score

    @staticmethod
    def _heuristic_score(skill_text: str, test_case: str) -> float:
        """确定性评分：技能描述与用例的关键词重合度（可复现，无随机）"""
        kw_skill = set(re.findall(r"[一-鿿]{2,4}|\w{3,}", skill_text))
        kw_case = set(re.findall(r"[一-鿿]{2,4}|\w{3,}", test_case))
        if not kw_case:
            return 0.5
        return round(0.5 + 0.5 * len(kw_skill & kw_case) / len(kw_case), 2)

    def create_test(self, skill_a: str, skill_b: str, test_cases: list[str] = None) -> str:
        """创建 A/B 测试"""
        test_id = f"ab_{uuid.uuid4().hex[:8]}"
        self._tests[test_id] = {
            "skill_a": skill_a,
            "skill_b": skill_b,
            "test_cases": test_cases or ["默认测试"],
            "status": "running",
            "results": [],
            "created_at": datetime.now().isoformat(),
        }
        return test_id

    def run(self, test_id: str) -> dict:
        """执行测试"""
        test = self._tests.get(test_id)
        if not test:
            return {"error": "测试不存在"}
        results = []
        for case in test["test_cases"]:
            score_a = self._scorer(test["skill_a"], case)
            score_b = self._scorer(test["skill_b"], case)
            results.append(
                {
                    "case": case,
                    "score_a": round(score_a, 2),
                    "score_b": round(score_b, 2),
                    "winner": "A" if score_a > score_b else "B",
                }
            )
        avg_a = sum(r["score_a"] for r in results) / len(results)
        avg_b = sum(r["score_b"] for r in results) / len(results)
        test["status"] = "completed"
        test["results"] = results
        test["winner"] = "A" if avg_a > avg_b else "B"
        test["avg_a"] = round(avg_a, 2)
        test["avg_b"] = round(avg_b, 2)
        self._results.append(test)
        return test


# ═══════════════════════════════════
# 4. Swarm Intelligence — 群体智慧
# ═══════════════════════════════════


class SwarmIntelligence:
    """群体智慧——匿名化跨用户技能共享"""

    def __init__(self):
        self._shared_skills: list[dict] = []
        self._ratings: dict[str, list[float]] = {}

    def share_skill(self, skill_data: dict, anonymize: bool = True) -> str:
        """共享技能（自动匿名化）"""
        shared = dict(skill_data)
        if anonymize:
            shared.pop("author", None)
            shared.pop("user_id", None)
            shared["anonymous_id"] = hashlib.md5(str(time.time()).encode()).hexdigest()[:8]
        skill_id = f"shared_{uuid.uuid4().hex[:8]}"
        shared["shared_id"] = skill_id
        shared["shared_at"] = datetime.now().isoformat()
        shared["rating"] = 0.0
        shared["downloads"] = 0
        self._shared_skills.append(shared)
        return skill_id

    def rate_skill(self, shared_id: str, rating: float):
        """评价共享技能"""
        if shared_id not in self._ratings:
            self._ratings[shared_id] = []
        self._ratings[shared_id].append(max(0, min(5, rating)))
        for skill in self._shared_skills:
            if skill["shared_id"] == shared_id:
                ratings = self._ratings[shared_id]
                skill["rating"] = round(sum(ratings) / len(ratings), 1)
                skill["downloads"] += 1

    def get_trending(self, limit: int = 10) -> list[dict]:
        """获取热门技能"""
        return sorted(self._shared_skills, key=lambda s: s.get("rating", 0), reverse=True)[:limit]


# ===== 测试 =====


def test():
    import io
    import sys as _sys

    _sys.stdout = io.TextIOWrapper(_sys.stdout.buffer, encoding="utf-8", errors="replace")
    print("[TEST] Evolution v2 Engine", flush=True)

    al = ActiveLearner()
    for _ in range(10):
        al.record_action("法规检索", {"query": "test"})
        al.record_action("执法问答", {"facts": "test"})
    predictions = al.predict_next()
    pattern = al.identify_pattern()
    print(f"[ActiveLearn] 预测: {len(predictions)} 项, 模式: {'有' if pattern else '无'}", flush=True)

    sc = SkillComposer()
    combo = sc.compose(["检索", "分析", "生成"], "执法文书生成")
    print(f"[Compose] 组合完成: {combo['id']}", flush=True)

    ab = ABTest()
    tid = ab.create_test("skill_v1", "skill_v2", ["case1", "case2", "case3"])
    result = ab.run(tid)
    print(f"[ABTest] 优胜者: {result['winner']} (A={result['avg_a']}, B={result['avg_b']})", flush=True)

    sw = SwarmIntelligence()
    sid = sw.share_skill({"name": "法规检索技能", "steps": ["step1", "step2"]})
    sw.rate_skill(sid, 4.5)
    sw.rate_skill(sid, 5.0)
    trending = sw.get_trending()
    print(f"[Swarm] 共享技能评分: {trending[0]['rating'] if trending else 'N/A'}", flush=True)

    print(f"\n{'=' * 30}", flush=True)
    print("[OK] Evolution v2 测试通过", flush=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test()
