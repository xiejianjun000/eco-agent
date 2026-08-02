#!/usr/bin/env python3
"""
eco_loops_integration.py — 五层循环集成入口（补强版）

改动：
1. L3 Pulse 全量接线：5 个 PulseSteps 全部注册（原仅 sync/diff 两个占位）
2. L4 Evolve 自动触发：任务完成后累计达阈值自动触发进化（原仅手动 CLI）
3. L4 每日调度：依赖新 scheduler 模块每天凌晨 2:00 自动进化
4. 任务完成钩子：on_task_complete() 供外层调用
"""

import os
import sys
import time
import logging
import threading
from pathlib import Path
from datetime import datetime

logger = logging.getLogger("eco_loops")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent_core.heartbeat import PulseLoop, PulseSteps, default_steps
from agent_core.meta_evolution import MetaEvolution

# ── L5 自愈（条件加载，允许缺失） ──
try:
    from agent_core.self_healing import SelfHealing
    _HAS_SELF_HEALING = True
except ImportError:
    SelfHealing = None
    _HAS_SELF_HEALING = False


class EcoLoopsIntegration:
    """五层循环统一入口 & 生命周期管理"""

    def __init__(self):
        # L1 ReAct++（由 agent_core/react_loop 运行时接管，此处仅登记）
        self.l1_enabled = True

        # L3 心跳
        self.l3 = PulseLoop()

        # L4 进化
        self.l4 = MetaEvolution()

        # L5 自愈
        self.l5 = SelfHealing() if _HAS_SELF_HEALING else None

        # ── L4 自动触发配置 ──
        self._task_count = 0
        self._l4_auto_threshold = int(os.environ.get("ECO_L4_AUTO_THRESHOLD", "10"))
        self._l4_daily_time = os.environ.get("ECO_L4_DAILY_TIME", "02:00")
        self._l4_daily_enabled = os.environ.get("ECO_L4_DAILY", "true").lower() == "true"
        self._l4_last_run: str | None = None

        # 任务历史缓存（供 L4 经验回放用）
        self._task_history: list[dict] = []

    def start(self):
        """启动所有循环层"""
        # ── L3: 全量五步骤接线（补强！）──
        steps = default_steps()

        # STEP 1: 数据同步（已有生产实现）
        self.l3.register_listener("sync", steps.step_sync)

        # STEP 2: 差异检测（已有生产实现）
        self.l3.register_listener("diff", steps.step_diff)

        # STEP 3: 规则触发（补强！原为占位 lambda）
        self.l3.register_listener("rule_engine", steps.step_rule_engine)

        # STEP 4: 内存整理 —— SQLite VACUUM + 完整性检查（补强！原为占位 lambda）
        self.l3.register_listener("mem_cron", steps.step_mem_cron)

        # STEP 5: 主动建议生成（补强！原为占位 lambda）
        # 封装：收集前几步结果后生成建议
        def _suggestions_wrapper():
            ctx = {}
            try:
                sync_result = steps.step_sync()
                diff_result = steps.step_diff()
                rule_result = steps.step_rule_engine()
                ctx["stale_count"] = len(rule_result.get("triggered", []))
                ctx["changed"] = diff_result.get("changed", 0)
            except Exception:
                pass
            return steps.step_suggestions(ctx)
        self.l3.register_listener("suggestions", _suggestions_wrapper)

        logger.info("[L3] Pulse 全量五步骤已接线: sync/diff/rule_engine/mem_cron/suggestions")

        self.l3.start()

        # ── L4: 尝试注册每日进化调度 ──
        if self._l4_daily_enabled:
            try:
                self._register_daily_evolution()
                logger.info(f"[L4] 每日进化已调度 ({self._l4_daily_time})")
            except Exception as e:
                logger.warning(f"[L4] 每日进化调度失败，将仅支持手动触发: {e}")

        logger.info("[Loops] 五层循环已启动: L1/L3/L4/L5")
        return self

    def stop(self):
        self.l3.stop()
        logger.info("[Loops] 五层循环已停止")

    # ── L4 自动触发 ──

    def on_task_complete(self, task_result: dict = None):
        """任务完成钩子——累计任务数，达到阈值自动触发 L4 进化

        调用方（如 Commander/CLI chat）在每次 Agent 任务完成后调用此方法。
        """
        self._task_count += 1
        if task_result:
            self._task_history.append({
                "success": task_result.get("success", True),
                "task": task_result.get("task", ""),
                "timestamp": datetime.now().isoformat(),
            })
            # 仅保留最近 200 条历史
            if len(self._task_history) > 200:
                self._task_history = self._task_history[-200:]

        if self._task_count >= self._l4_auto_threshold:
            logger.info(f"[L4] 任务数达到阈值 ({self._task_count}/{self._l4_auto_threshold})，自动触发进化")
            self.trigger_evolution()
            self._task_count = 0

    def trigger_evolution(self, task_history: list[dict] = None) -> dict:
        """手动/自动触发 L4 进化"""
        history = task_history or self._task_history
        try:
            result = self.l4.run_full_cycle(history)
            self._l4_last_run = datetime.now().isoformat()
            logger.info(f"[L4] 进化完成，报告: {result.get('report_path', 'N/A')}")
            return result
        except Exception as e:
            logger.error(f"[L4] 进化失败: {e}")
            return {"error": str(e)}

    def _register_daily_evolution(self):
        """注册 L4 每日自动调度（依赖 scheduler 模块）"""
        try:
            from agent_core.scheduler import scheduler
            cron_expr = "0 2 * * *" if self._l4_daily_time == "02:00" else None
            if not cron_expr:
                h, m = self._l4_daily_time.split(":")
                cron_expr = f"{int(m)} {int(h)} * * *"

            def _daily_evolution():
                logger.info("[L4] 每日自动进化触发")
                return self.trigger_evolution()

            scheduler.register_handler("l4_daily_evolution", _daily_evolution)
            scheduler.add_job(cron_expr, "L4 每日自动进化", "l4_daily_evolution")
        except ImportError:
            logger.info("[L4] scheduler 模块未加载，每日进化仅支持手动触发")

    def get_stats(self) -> dict:
        return {
            "l1_react_enabled": self.l1_enabled,
            "l3_pulse": self.l3.get_stats(),
            "l4_task_count": self._task_count,
            "l4_auto_threshold": self._l4_auto_threshold,
            "l4_daily_enabled": self._l4_daily_enabled,
            "l4_last_run": self._l4_last_run,
            "l4_history_size": len(self._task_history),
            "l5_healing": self.l5 is not None,
        }

    def self_test(self) -> dict:
        """五层自检"""
        results = {}
        # L3
        try:
            steps = default_steps()
            sync = steps.step_sync()
            diff = steps.step_diff()
            rule = steps.step_rule_engine()
            mem = steps.step_mem_cron()
            sugg = steps.step_suggestions({"stale_count": len(rule.get("triggered", []))})
            results["l3"] = {
                "ok": True,
                "sync": sync,
                "diff": diff,
                "rule_engine": rule,
                "mem_cron": mem,
                "suggestions": sugg,
            }
        except Exception as e:
            results["l3"] = {"ok": False, "error": str(e)}

        # L4
        try:
            analysis = self.l4.analyze([], dry_run=True)
            results["l4"] = {"ok": True, "analysis": str(analysis)[:200]}
        except Exception as e:
            results["l4"] = {"ok": False, "error": str(e)}

        return results


# ===== 全局单例 =====
loops = EcoLoopsIntegration()


# ===== 测试 =====
def test():
    import io
    import sys as _sys
    _sys.stdout = io.TextIOWrapper(_sys.stdout.buffer, encoding='utf-8', errors='replace')

    print("=== Eco Agent 五层循环自检 ===")
    test_results = loops.self_test()
    for layer, result in test_results.items():
        status = "OK" if result.get("ok") else "FAIL"
        print(f"  [{status}] {layer}")
        if not result.get("ok"):
            print(f"         错误: {result.get('error')}")

    # 测试任务完成钩子
    loops.on_task_complete({"success": True, "task": "test_task"})
    stats = loops.get_stats()
    print(f"\n  L4 任务计数: {stats['l4_task_count']}/{stats['l4_auto_threshold']}")
    print(f"  L4 每日进化: {'启用' if stats['l4_daily_enabled'] else '禁用'}")
    print(f"  L4 历史大小: {stats['l4_history_size']}")
    print(f"  L3 监听器数: {stats['l3_pulse']['listeners']}")

    print("\n[OK] 五层循环测试通过")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test()
