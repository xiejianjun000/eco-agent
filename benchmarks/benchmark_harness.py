#!/usr/bin/env python3
"""
Eco Agent Benchmark Harness — Phase 6 基准测试框架

P-05: OSWorld 2.0 / HumanEval 基准测试

诚实原则（整改后）：
  - HumanEval / MBPP / OSWorld 需要外部评测 harness（本仓库未接入），
    一律如实标注 "not_run"，绝不产出随机/编造分数。
  - 内部指标（Token 压缩比、RAG 关键词保留率）用固定 fixture 实测，
    结果可复现、可审计。
"""

import json
import logging
import sys
import time
from pathlib import Path

logger = logging.getLogger("benchmark")
ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT / "memory-tree" / "data" / "benchmarks"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(ROOT))

# 外部基准：需要接入对应官方评测 harness 后才能产出真实分数
EXTERNAL_BENCHMARKS = {
    "human_eval": {"name": "HumanEval", "target": 94, "unit": "Pass@1 %"},
    "mbpp": {"name": "MBPP", "target": 90, "unit": "Pass@1 %"},
    "osworld": {"name": "OSWorld 2.0", "target": 72, "unit": "Score"},
}

# 内部可实测指标 fixture（固定文本，结果可复现）
_INTERNAL_FIXTURE = (
    "关键信息" * 2000 + "\n" + "\n".join(f"第{i}条重要数据：法规条文{i}规定了排放标准限值{i * 10}mg" for i in range(100))
)


class BenchmarkRunner:
    """基准测试执行器——外部基准如实标注 not_run，内部指标实测"""

    def run_all(self) -> dict:
        results: dict = {}
        for bid, info in EXTERNAL_BENCHMARKS.items():
            results[bid] = self._external_placeholder(bid, info)
        results["token_compression"] = self._run_token_compression()
        self._save(results)
        return results

    def _external_placeholder(self, bid: str, info: dict) -> dict:
        """外部基准未接入官方评测 harness——如实标注，不编造分数"""
        logger.info(f"[Benchmark] {info['name']}: 未接入官方评测 harness，标记 not_run")
        return {
            "name": info["name"],
            "score": None,
            "target": info["target"],
            "passed": None,
            "unit": info["unit"],
            "status": "not_run",
            "note": "外部评测 harness 未接入，无真实分数；骨架待接入",
        }

    def _run_token_compression(self) -> dict:
        """内部指标实测：压缩比 + RAG 关键词保留率（固定 fixture）"""
        from agent_core.data_sync import TokenCompressor

        tc = TokenCompressor()
        r = tc.compress(_INTERNAL_FIXTURE)
        acc = tc.rag_accuracy(_INTERNAL_FIXTURE, r["compressed"])
        return {
            "name": "TokenCompression+RAG(内部实测)",
            "score": acc,
            "compression_ratio": r["ratio"],
            "target": 0.9,
            "passed": acc >= 0.9,
            "unit": "关键词保留率",
            "status": "measured",
        }

    def _save(self, results: dict):
        path = RESULTS_DIR / f"benchmark_{time.strftime('%Y%m%d_%H%M')}.json"
        path.write_text(json.dumps(results, indent=2, ensure_ascii=False))
        logger.info(f"[Benchmark] 结果已保存: {path}")

    def report(self) -> str:
        lines = ["# Eco Agent 基准测试报告", "", "| 基准 | 分数 | 目标 | 状态 | 单位 |", "|:-----|:----:|:----:|:----:|:-----|"]
        data = {}
        files = sorted(RESULTS_DIR.glob("*.json"))
        if files:
            data = json.loads(files[-1].read_text())
        for bid, info in {
            **EXTERNAL_BENCHMARKS,
            "token_compression": {"name": "TokenCompression+RAG(内部实测)", "target": 0.9, "unit": "关键词保留率"},
        }.items():
            latest = data.get(bid)
            if not latest:
                lines.append(f"| {info['name']} | — | {info['target']} | 未运行 | {info['unit']} |")
            elif latest.get("status") == "not_run":
                lines.append(f"| {info['name']} | — | {info['target']} | not_run（骨架待接入） | {info['unit']} |")
            else:
                mark = "PASS" if latest["passed"] else "FAIL"
                lines.append(f"| {info['name']} | {latest['score']} | {info['target']} | {mark} | {info['unit']} |")
        return "\n".join(lines)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    br = BenchmarkRunner()
    r = br.run_all()
    for v in r.values():
        score = v["score"] if v["score"] is not None else "not_run"
        print(f"  {v['name']}: {score} (目标>{v['target']})")
    print()
    print(br.report())
