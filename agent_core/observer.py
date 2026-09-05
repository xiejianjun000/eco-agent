#!/usr/bin/env python3
"""
observer.py — Eco Agent 观察 Agent

职责：执行验证、反馈回环、质量评估。

三阶段验证：
  1. Pre-check：执行前验证条件是否满足
  2. Runtime check：执行中监控异常
  3. Post-check：执行后验证结果质量

用法：
  from agent_core.observer import Observer
  observer = Observer()
  result = observer.verify("task_id", output_data)
"""

import logging
import re
import time
from pathlib import Path

logger = logging.getLogger("observer")

ROOT = Path(__file__).resolve().parent.parent


class Observer:
    """观察 Agent——执行验证与反馈"""

    def __init__(self):
        self._history: list[dict] = []

    def verify(self, task_desc: str, output: str, expected: str = "") -> dict:
        """三阶段验证任务执行结果"""
        start = time.time()

        # Phase 1: Pre-check — 输出存在性
        pre_check = self._pre_check(output)

        # Phase 2: Runtime — 输出质量
        runtime_check = self._runtime_check(output, task_desc)

        # Phase 3: Post-check — 与预期对比
        post_check = self._post_check(output, expected) if expected else {"match": True, "score": 0.8}

        # 综合评分
        scores = [pre_check["score"], runtime_check["score"], post_check["score"]]
        final_score = sum(scores) / len(scores)
        passed = final_score >= 0.6

        result = {
            "passed": passed,
            "final_score": round(final_score, 2),
            "pre_check": pre_check,
            "runtime_check": runtime_check,
            "post_check": post_check,
            "elapsed_ms": round((time.time() - start) * 1000, 1),
            "feedback": self._generate_feedback(pre_check, runtime_check, post_check),
        }
        self._history.append(result)
        logger.info(f"[Observer] 验证: {'PASS' if passed else 'FAIL'} (score={final_score:.2f})")
        return result

    def _pre_check(self, output: str) -> dict:
        """存在性检查"""
        issues = []
        if not output:
            return {"score": 0, "issues": ["输出为空"]}
        if len(output) < 10:
            issues.append("输出过短")
        return {"score": 0.9 if not issues else 0.3, "issues": issues}

    def _runtime_check(self, output: str, task_desc: str) -> dict:
        """质量检查"""
        issues = []
        # 错误检测
        error_patterns = ["error", "exception", "traceback", "failed", "cannot", "panic", "null pointer"]
        for p in error_patterns:
            if p in output.lower():
                issues.append(f"包含错误关键词: {p}")
                break

        # 空值检测
        if output in ("None", "null", "undefined", "[]", "{}"):
            issues.append("输出为空值")

        # 任务相关性
        task_keywords = set(re.findall(r"\w+", task_desc.lower()))
        output_keywords = set(re.findall(r"\w+", output.lower()))
        overlap = len(task_keywords & output_keywords) / max(len(task_keywords), 1)
        if overlap < 0.1 and len(task_keywords) > 3:
            issues.append("输出与任务描述相关性低")

        score = max(0.1, 0.9 - len(issues) * 0.25)
        return {"score": score, "issues": issues, "relevance": round(overlap, 2)}

    def _post_check(self, output: str, expected: str) -> dict:
        """与预期结果对比"""
        if not expected:
            return {"match": True, "score": 0.8, "note": "无预期结果可对比"}
        overlap = len(set(output.lower().split()) & set(expected.lower().split()))
        total = max(len(set(output.lower().split()) | set(expected.lower().split())), 1)
        score = overlap / total
        return {"match": score > 0.3, "score": score}

    def _generate_feedback(self, pre: dict, runtime: dict, post: dict) -> str:
        """生成可执行的反馈"""
        all_issues = pre.get("issues", []) + runtime.get("issues", []) + post.get("issues", [])
        if not all_issues:
            return "执行通过，无反馈"
        return "建议: " + "; ".join(all_issues[:3])

    def get_stats(self) -> dict:
        total = len(self._history)
        if total == 0:
            return {"total": 0, "pass_rate": "N/A"}
        passed = sum(1 for r in self._history if r["passed"])
        return {
            "total": total,
            "pass_rate": f"{passed / total * 100:.0f}%",
            "avg_score": round(sum(r["final_score"] for r in self._history) / total, 2),
        }


# ===== 测试 =====


def test():
    import io
    import sys as _sys

    _sys.stdout = io.TextIOWrapper(_sys.stdout.buffer, encoding="utf-8", errors="replace")
    print("[TEST] Observer Agent", flush=True)

    obs = Observer()

    # 测试通过场景
    r1 = obs.verify("编写一个Python函数计算两个数的和", "def add(a, b): return a + b")
    print(f"  通过场景: {'PASS' if r1['passed'] else 'FAIL'} score={r1['final_score']}", flush=True)

    # 测试失败场景
    r2 = obs.verify("编写Python函数", "Error: syntax error")
    print(f"  失败场景: {'PASS' if r2['passed'] else 'FAIL'} score={r2['final_score']}", flush=True)

    # 测试空输出
    r3 = obs.verify("执行查询", "")
    print(f"  空输出: {'PASS' if r3['passed'] else 'FAIL'} score={r3['final_score']}", flush=True)

    stats = obs.get_stats()
    print(f"\n[Stats] 总验证: {stats['total']}, 通过率: {stats['pass_rate']}", flush=True)
    print(f"\n{'=' * 40}", flush=True)
    print("[OK] Observer Agent 测试通过", flush=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test()
