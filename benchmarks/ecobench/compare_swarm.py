#!/usr/bin/env python3
"""
ecobench_swarm_compare.py — EcoBench 抽测：单 Agent vs 三角色协作模式对比（B1）

同一批题（默认前 5 题，控制成本），分别用：
  single：单次 LLM 调用（同 run_ecobench 无 RAG 口径）
  swarm ：三角色协作（RoleSwarm.run，synthesis 作为答案）
用 benchmarks/ecobench/run_ecobench.score_item 同一评分口径如实打分。

用法: python benchmarks/ecobench/compare_swarm.py --limit 5
"""

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from benchmarks.ecobench.run_ecobench import SYSTEM, load_dataset, score_item  # noqa: E402

OUT = Path(__file__).resolve().parent / "ecobench_swarm_compare.json"


def macro(scored: list[dict]) -> dict:
    n = max(len(scored), 1)
    return {
        "n": len(scored),
        "citation_accuracy": round(sum(s["citation_hit"] for s in scored) / n, 4),
        "keypoint_f1": round(sum(s["keypoint_f1"] for s in scored) / n, 4),
    }


def run_single(client, item):
    resp = client.chat(
        [{"role": "system", "content": SYSTEM},
         {"role": "user", "content": item["question"]}])
    return (resp.get("choices", [{}])[0].get("message", {}).get("content", "") or "").strip()


def run_swarm(swarm, item):
    r = swarm.run(item["question"])
    return r["synthesis"].strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=5)
    args = ap.parse_args()

    from agent_core.llm_client import get_default_client
    from agent_core.role_swarm import RoleSwarm
    client = get_default_client()
    if not client.available():
        print("[compare] LLM 不可用")
        return 1
    swarm = RoleSwarm(client=client)
    items = load_dataset(args.limit)
    report = {"limit": len(items), "ts": time.strftime("%Y-%m-%d %H:%M:%S"), "modes": {}}

    for mode, fn in (("single", run_single), ("swarm", run_swarm)):
        scored = []
        for i, item in enumerate(items, 1):
            t0 = time.time()
            ans = fn(swarm if mode == "swarm" else client, item)
            s = score_item(ans, item)
            scored.append(s)
            print(f"[{mode} {i}/{len(items)}] cite={s['citation_hit']:.2f} kpF1={s['keypoint_f1']:.2f} "
                  f"({time.time()-t0:.0f}s)", flush=True)
        report["modes"][mode] = macro(scored)
        print(f"[{mode}] {report['modes'][mode]}", flush=True)

    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[compare] 报告已写入 {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
