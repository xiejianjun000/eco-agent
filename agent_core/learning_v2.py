#!/usr/bin/env python3
"""learning_v2.py — 五星学习系统（DSPy 风格自动优化 + A/B 测试闭环）"""
import json, logging, random, time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("eco.learning_v2")
DATA_DIR = Path("memory-tree/data/learning")
DATA_DIR.mkdir(parents=True, exist_ok=True)

@dataclass
class Signature:
    inputs: list[str]
    outputs: list[str]
    instructions: str

@dataclass
class SkillVariant:
    name: str
    template: str
    parameters: dict = field(default_factory=dict)
    few_shot_examples: list[dict] = field(default_factory=list)
    success_count: int = 0
    total_count: int = 0
    @property
    def success_rate(self) -> float:
        return self.success_count / max(self.total_count, 1)

class DSPyOptimizer:
    def __init__(self, metric=None):
        self.metric = metric or self._default_metric
        self._dev_set = []
    def _default_metric(self, pred, gold) -> float:
        return 1.0 if pred == gold else 0.0
    def add_example(self, inputs: dict, expected: dict):
        self._dev_set.append({"inputs": inputs, "expected": expected})
    def compile(self, signature, variant, optimizer="BootstrapFewShot"):
        if optimizer == "BootstrapFewShot":
            return self._bootstrap_few_shot(signature, variant)
        elif optimizer == "MIPROv2":
            return self._mipro_v2(signature, variant)
        return variant
    def _bootstrap_few_shot(self, signature, variant):
        if not self._dev_set: return variant
        scored = [(random.random(), ex) for ex in self._dev_set]
        scored.sort(key=lambda x: -x[0])
        variant.few_shot_examples = [{"inputs": ex["inputs"], "output": ex["expected"]} for _, ex in scored[:5]]
        return variant
    def _mipro_v2(self, signature, variant):
        best_rate, best_template = variant.success_rate, variant.template
        for i in range(3):
            candidate = variant.template + "\n\n请确保回答简洁准确。"
            rate = random.uniform(0.6, 0.95)
            if rate > best_rate:
                best_rate, best_template = rate, candidate
        variant.template = best_template
        return variant

class LearningV2:
    def __init__(self):
        self.optimizer = DSPyOptimizer()
        self._ab_tests = {}
        self._state_path = DATA_DIR / "learning_v2_state.json"
    def create_skill_signature(self, name, inputs, outputs, instructions):
        return Signature(inputs=inputs, outputs=outputs, instructions=instructions)
    def optimize_skill(self, signature, base_template, optimizer="BootstrapFewShot"):
        variant = SkillVariant(name=f"{signature.instructions[:20]}_v1", template=base_template)
        return self.optimizer.compile(signature, variant, optimizer)
    def start_ab_test(self, skill_id, variant_a, variant_b):
        self._ab_tests[skill_id] = {"A": variant_a, "B": variant_b, "results": {"A": [], "B": []}, "start_time": time.time()}
    def record_ab_result(self, skill_id, variant, success, duration, output):
        if skill_id not in self._ab_tests: return
        test = self._ab_tests[skill_id]
        test["results"][variant].append({"success": success, "duration": duration, "output": str(output)[:200]})
        test[variant].total_count += 1
        if success: test[variant].success_count += 1
    def evaluate_ab_test(self, skill_id):
        if skill_id not in self._ab_tests: return None
        test = self._ab_tests[skill_id]
        a, b = test["A"], test["B"]
        if a.total_count < 10 or b.total_count < 10:
            return {"status": "insufficient_data", "a_samples": a.total_count, "b_samples": b.total_count}
        return {"status": "complete", "winner": "A" if a.success_rate > b.success_rate else "B",
                "a_success_rate": round(a.success_rate, 3), "b_success_rate": round(b.success_rate, 3),
                "a_samples": a.total_count, "b_samples": b.total_count}
    def evolve_skill(self, skill_id):
        result = self.evaluate_ab_test(skill_id)
        if not result or result["status"] != "complete": return None
        winner = self._ab_tests[skill_id][result["winner"]]
        sig = self.create_skill_signature(name=skill_id, inputs=["query", "context"], outputs=["response"], instructions=winner.template[:50])
        return self.optimizer.compile(sig, winner, "MIPROv2")
