#!/usr/bin/env python3
"""
smoke_kimi.py — 真实 Kimi LLM 冒烟测试

覆盖 LLM 接入点（单测走 ECO_LLM_DISABLE 规则降级，真实调用由本脚本验证）：
  1. L1 ReAct++ 循环（Kimi 思考 + 置信度评估）
  2. L4 进化报告（Kimi 元认知分析）

用法：
  cp .env.example .env   # 填入 KIMI_API_KEY
  python scripts/smoke_kimi.py
"""

import sys
import logging
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent_core.llm_client import get_default_client
from agent_core.react_loop import ReActPlusPlus, ReActState
from agent_core.meta_evolution import MetaEvolution

logging.basicConfig(level=logging.WARNING)


def main():
    client = get_default_client()
    print(f"[Smoke] LLM available={client.available()} model={client.model}")
    if not client.available():
        print("[FAIL] LLM 不可用：请检查 .env 中 KIMI_API_KEY，且不要设置 ECO_LLM_DISABLE=1")
        sys.exit(1)

    # Smoke-1: L1 ReAct++ 循环（真实 LLM 思考 + 置信度）
    print("[Smoke-1] L1 ReAct++ 循环（Kimi 思考 + 置信度评估）")
    loop = ReActPlusPlus()
    loop.register_tool("search", lambda query: f"[搜索] 找到关于'{query}'的结果", "搜索工具")
    result = loop.execute("查询大气污染防治法第99条内容")
    print(f"  steps={result['steps']} confidence={result['confidence']} time={result['total_time_ms']:.0f}ms")
    st = ReActState(step=1, observation="查询大气污染防治法第99条内容")
    t = loop._think(st, {})
    print(f"  LLM thought 原文: {t[:80]}")
    is_template = t.startswith("理解任务:")
    print(f"  是否规则模板: {is_template}")
    assert not is_template, "思考仍是规则模板，LLM 未真正接入"
    assert result["confidence"] > 0

    # Smoke-2: L4 进化报告（真实 LLM 元认知分析）
    print("[Smoke-2] L4 进化报告（Kimi 元认知分析）")
    evo = MetaEvolution()
    history = [{"success": i % 4 != 3, "task": f"task_{i}"} for i in range(8)]
    res = evo.run_full_cycle(history)
    report = Path(res["report_path"]).read_text(encoding="utf-8")
    has_llm = "元认知分析（LLM 生成）" in report
    print(f"  含 LLM 元认知分析节: {has_llm}")
    if has_llm:
        idx = report.index("## 元认知分析")
        print("  -- LLM 元认知分析摘录 --")
        print("\n".join("  " + l for l in report[idx:].splitlines()[2:6]))
    assert has_llm, "进化报告缺少 LLM 元认知分析章节"

    print("[OK] Kimi 冒烟测试全部通过")


if __name__ == "__main__":
    main()
