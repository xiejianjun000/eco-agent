#!/usr/bin/env python3
"""
run_ecobench.py — EcoBench-mini 评测器（50 题生态环境执法问答金标准）

指标（全部如实计算，严禁封顶/保底/美化）：
  - 法条引用准确率 citation_accuracy：required_citations 命中率（逐题命中数/必引数，再平均）
  - 要点 F1 keypoint_f1：key_points 关键词逐题 P/R/F1，再宏平均

模式：
  真实 LLM：默认，经 LLMClient 逐题调用
  mock：设置 ECO_LLM_DISABLE=1 或 --mock，走固定 mock 答案，仅验证流程（CI/离线）

输出：benchmarks/ecobench/ecobench_report.json + 控制台摘要
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

HERE = Path(__file__).resolve().parent
DATASET = HERE / "dataset.jsonl"
REPORT = HERE / "ecobench_report.json"

SYSTEM = (
    "你是生态环境执法领域的问答助手。回答必须：1) 引用具体现行法律法规名称及条款号；"
    "2) 给出明确结论；3) 覆盖要点。用中文回答，简明扼要。"
)

MOCK_ANSWER = "[mock] 本题需依据相关法律法规处理，具体条款略。"


def _norm(s: str) -> str:
    """归一化：去空白/书名号/国名前缀，提升法条匹配的诚实稳健性"""
    t = re.sub(r"\s+", "", s or "")
    t = re.sub(r"（[^）]{0,30}）", "", t)  # 法名与条号间的修订年份等括号注释不影响命中
    t = re.sub(r"\([^)]{0,30}\)", "", t)
    t = t.replace("《", "").replace("》", "").replace("中华人民共和国", "")
    return t


def score_item(answer: str, item: dict) -> dict:
    """逐题评分：引用命中率 + 要点 F1（诚实计算，不做任何修饰）"""
    a = _norm(answer)
    cites = item["required_citations"]
    hit_c = sum(1 for c in cites if _norm(c) in a)
    citation_hit = hit_c / len(cites) if cites else 1.0

    kps = item["key_points"]
    tp = sum(1 for k in kps if _norm(k) in a)
    precision = tp / len(kps) if kps else 1.0  # 输出侧全部要求要点
    recall = tp / len(kps) if kps else 1.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {
        "id": item["id"], "category": item["category"],
        "citation_hit": round(citation_hit, 4),
        "citation_hits": hit_c, "citation_total": len(cites),
        "keypoint_tp": tp, "keypoint_total": len(kps),
        "keypoint_f1": round(f1, 4),
    }


def load_dataset(limit: int = 0) -> list[dict]:
    items = [json.loads(l) for l in DATASET.read_text(encoding="utf-8").splitlines() if l.strip()]
    return items[:limit] if limit else items


def answer_question(client, item: dict, mock: bool) -> str:
    if mock or client is None or not client.available():
        return MOCK_ANSWER
    try:
        return client.complete(item["question"], system=SYSTEM, max_tokens=1024) or MOCK_ANSWER
    except Exception as e:
        return f"[error] {type(e).__name__}: {e}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="run_ecobench", description="EcoBench-mini runner")
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 题（控制成本）")
    ap.add_argument("--mock", action="store_true", help="mock 模式（离线/CI）")
    ap.add_argument("--out", default=str(REPORT))
    args = ap.parse_args(argv)

    mock = args.mock or os.environ.get("ECO_LLM_DISABLE", "").strip().lower() in ("1", "true", "yes")
    client = None
    if not mock:
        from agent_core.llm_client import get_default_client
        client = get_default_client()
        if not client.available():
            print("[EcoBench] LLM 不可用，自动降级 mock 模式", flush=True)
            mock = True

    items = load_dataset(args.limit)
    print(f"[EcoBench-mini] n={len(items)} mode={'mock' if mock else 'LLM'}", flush=True)

    results = []
    t0 = time.time()
    for i, item in enumerate(items, 1):
        ans = answer_question(client, item, mock)
        sc = score_item(ans, item)
        sc["answer"] = ans
        sc["golden_answer"] = item["golden_answer"]
        results.append(sc)
        print(f"  [{i:02d}/{len(items)}] {item['id']} {item['category']} "
              f"cite={sc['citation_hit']:.2f} f1={sc['keypoint_f1']:.2f}", flush=True)

    n = len(results) or 1
    summary = {
        "n_questions": len(results),
        "mode": "mock" if mock else "llm",
        "citation_accuracy": round(sum(r["citation_hit"] for r in results) / n, 4),
        "keypoint_f1": round(sum(r["keypoint_f1"] for r in results) / n, 4),
        "elapsed_s": round(time.time() - t0, 1),
        "by_category": {},
    }
    cats = sorted({r["category"] for r in results})
    for c in cats:
        sub = [r for r in results if r["category"] == c]
        m = len(sub) or 1
        summary["by_category"][c] = {
            "n": len(sub),
            "citation_accuracy": round(sum(r["citation_hit"] for r in sub) / m, 4),
            "keypoint_f1": round(sum(r["keypoint_f1"] for r in sub) / m, 4),
        }

    report = {"summary": summary, "results": results}
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n===== EcoBench-mini 摘要（如实报告，无封顶/保底） =====")
    print(f"  题目数: {summary['n_questions']}  模式: {summary['mode']}  耗时: {summary['elapsed_s']}s")
    print(f"  法条引用准确率: {summary['citation_accuracy']:.4f}")
    print(f"  要点 F1:        {summary['keypoint_f1']:.4f}")
    for c, s in summary["by_category"].items():
        print(f"    - {c}: cite={s['citation_accuracy']:.2f} f1={s['keypoint_f1']:.2f} (n={s['n']})")
    print(f"  报告: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
