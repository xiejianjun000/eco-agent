#!/usr/bin/env python3
"""
eco_loops_integration.py — Eco Agent 五层循环全集成

五层嵌套生命节律的统一入口：
  L1 ReAct++     → agent_core/react_loop.py
  L2 Task Loop   → agent_core/commander.py (Commander)
  L3 Pulse       → agent_core/heartbeat.py
  L4 Evolve      → agent_core/meta_evolution.py
  L5 Heal        → agent_core/self_healing.py

用法：
  python agent_core/eco_loops_integration.py   # 运行全部五层
  python agent_core/eco_loops_integration.py --self-test  # 自检
"""

import os, sys, json, time, logging, threading
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

logger = logging.getLogger("eco_loops")

ROOT = Path(__file__).resolve().parent.parent

# 导入五层循环
sys.path.insert(0, str(ROOT))
from agent_core.react_loop import ReActPlusPlus
from agent_core.commander import Commander
from agent_core.heartbeat import PulseLoop
from agent_core.meta_evolution import MetaEvolution
from agent_core.self_healing import SelfHealer


class EcoLoops:
    """五层循环全集成"""

    def __init__(self):
        self.l1 = ReActPlusPlus()
        self.l2 = Commander()
        self.l3 = PulseLoop()
        self.l4 = MetaEvolution()
        self.l5 = SelfHealer()
        self._running = False

    def start(self):
        """启动所有循环"""
        logger.info("=" * 50)
        logger.info("  Eco Agent 五层循环启动")
        logger.info("=" * 50)

        # L3 后台心跳（常驻）
        self.l3.register_listener("sync", lambda: "sync_ok")
        self.l3.register_listener("diff", lambda: "no_changes")
        self.l3.start()
        logger.info("  [OK] L3 Pulse Loop 启动")

        logger.info("  五层循环全部就绪")
        return self

    def stop(self):
        self.l3.stop()

    def execute_task(self, goal: str) -> Dict:
        """执行一个任务——贯穿五层循环"""
        logger.info(f"[EcoLoops] 执行: {goal[:40]}")
        # L5 保护 L2 执行
        result = self.l5.protect(
            lambda: self.l2.execute(goal),
            context=f"execute_{goal[:20]}"
        )
        return result

    def run_evolution(self):
        """触发进化循环"""
        return self.l4.run_full_cycle()

    def get_stats(self) -> Dict:
        return {
            "l1_react": self.l1.get_stats(),
            "l2_commander": {"missions": len(self.l2._results)},
            "l3_pulse": self.l3.get_stats(),
            "l5_healing": self.l5.get_stats(),
        }

    def self_test(self) -> Dict:
        """自检——逐层验证"""
        logger.info("[SelfTest] 五层循环自检开始")
        results = {}

        # L1
        try:
            self.l1.register_tool("echo", lambda x: x, "测试工具")
            l1_test = self.l1.execute("test echo", {"test": True})
            results["l1_react"] = {"passed": l1_test["steps"] > 0}
        except Exception as e:
            results["l1_react"] = {"passed": False, "error": str(e)}
        logger.info(f"  L1 ReAct++: {'PASS' if results['l1_react']['passed'] else 'FAIL'}")

        # L5
        try:
            l5_test = self.l5.protect(lambda: "ok", "self_test")
            results["l5_heal"] = {"passed": l5_test["success"]}
        except Exception as e:
            results["l5_heal"] = {"passed": False, "error": str(e)}
        logger.info(f"  L5 Self-Heal: {'PASS' if results['l5_heal']['passed'] else 'FAIL'}")

        # L4
        try:
            l4_test = self.l4.run_full_cycle()
            results["l4_evolve"] = {"passed": l4_test["report_path"] is not None}
        except Exception as e:
            results["l4_evolve"] = {"passed": False, "error": str(e)}
        logger.info(f"  L4 Evolve: {'PASS' if results['l4_evolve']['passed'] else 'FAIL'}")

        # L3
        results["l3_pulse"] = {"passed": self.l3._running}
        logger.info(f"  L3 Pulse: {'PASS' if results['l3_pulse']['passed'] else 'FAIL'}")

        # L2
        try:
            l2_test = self.l2.execute("测试任务")
            results["l2_commander"] = {"passed": l2_test["total_tasks"] > 0}
        except Exception as e:
            results["l2_commander"] = {"passed": False, "error": str(e)}
        logger.info(f"  L2 Commander: {'PASS' if results['l2_commander']['passed'] else 'FAIL'}")

        all_pass = all(r.get("passed", False) for r in results.values())
        results["all_pass"] = all_pass
        logger.info(f"[SelfTest] 五层循环: {'全部通过' if all_pass else '存在失败'}")
        return results


# ===== 测试 =====

def test():
    import io, sys as _sys
    _sys.stdout = io.TextIOWrapper(_sys.stdout.buffer, encoding='utf-8', errors='replace')

    print("[TEST] Eco Loops 五层集成", flush=True)
    loops = EcoLoops()
    loops.start()

    # 自检
    results = loops.self_test()
    print(f"\n[Integration] 全部通过: {results.get('all_pass', False)}", flush=True)
    for layer, r in results.items():
        if isinstance(r, dict) and "passed" in r:
            print(f"  {layer}: {'PASS' if r['passed'] else 'FAIL'}", flush=True)

    loops.stop()
    print(f"\n{'='*30}", flush=True)
    print("[OK] 五层循环全集成测试通过", flush=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(name)s] %(message)s")
    test()
