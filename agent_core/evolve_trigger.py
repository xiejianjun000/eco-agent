#!/usr/bin/env python3
"""
evolve_trigger.py — L4 Evolve 自动触发钩子

补上 README 自标的缺口：「每次任务后 / 每日自动触发：未实现，
无任务完成钩子与每日调度接线」。

数据流：
  L2 mission 结束 → record_mission() 沉淀 (expectation, output, verdict) 三元组
    → maybe_trigger() 满足条件自动调 MetaEvolution.run_full_cycle()

触发条件（全部满足）：
  1. 显式启用：ECO_AUTO_EVOLVE=1（方案A一致性，默认关闭不烧资源）
  2. 经验积累达阈值（默认 5 条；含失败任务的经验双倍计——失败最有进化价值）
  3. 冷却期已过（默认 4 小时，防频繁进化）

每日调度：should_evolve_daily() 供外部调度器（如 L3 Pulse）每日检查。

状态目录：默认 memory-tree/data/evolution/（ECO_EVOLVE_STATE_DIR 可覆盖）。
"""

import json
import logging
import os
import time
from pathlib import Path
from datetime import datetime

logger = logging.getLogger("evolve_trigger")

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STATE_DIR = ROOT / "memory-tree" / "data" / "evolution"


class EvolveTrigger:
    """L4 自动触发器：经验沉淀 + 条件判断 + 调起 Evolve"""

    def __init__(self, state_dir: Path | None = None, evolve_runner=None,
                 threshold: int | None = None, cooldown_s: float = 4 * 3600):
        self._dir = Path(state_dir or os.environ.get("ECO_EVOLVE_STATE_DIR")
                         or DEFAULT_STATE_DIR)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._jsonl = self._dir / "experience.jsonl"
        self._state = self._dir / "trigger_state.json"
        self._runner = evolve_runner or self._default_runner
        self._threshold = threshold if threshold is not None else int(
            os.environ.get("ECO_EVOLVE_THRESHOLD", "5"))
        self._cooldown = cooldown_s

    # ── 经验沉淀 ──

    def record_mission(self, summary: dict, tasks: list) -> dict:
        """L2 mission 结束沉淀经验：(expectation, output, verdict, status) 三元组"""
        entry = {
            "recorded_at": datetime.now().isoformat(),
            "summary": summary,
            "tasks": [{
                "description": getattr(t, "description", "")[:80],
                "status": str(getattr(t, "status", "")),
                "expectation": getattr(t, "expectation", ""),
                "output": str(getattr(t, "output", ""))[:500],
                "verdict": getattr(t, "verdict", ""),
            } for t in tasks],
        }
        with open(self._jsonl, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    def _load_experiences(self) -> list[dict]:
        if not self._jsonl.exists():
            return []
        out = []
        for line in self._jsonl.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out

    # ── 触发条件 ──

    def _evolve_weight(self) -> float:
        """经验权重：含失败任务的 mission 双倍计（失败是差距分析的最佳原料）"""
        weight = 0.0
        for e in self._load_experiences():
            weight += 2.0 if e.get("summary", {}).get("failed", 0) > 0 else 1.0
        return weight

    def _last_run(self) -> float:
        try:
            return json.loads(self._state.read_text()).get("last_run_ts", 0.0)
        except Exception:
            return 0.0

    def _stamp_last_run(self, ts: float | None = None):
        self._state.write_text(json.dumps({"last_run_ts": ts or time.time()}))

    def _cooled_down(self) -> bool:
        return (time.time() - self._last_run()) >= self._cooldown

    def should_evolve_daily(self) -> bool:
        """每日调度检查：距上次进化 >24h（含从未进化过）"""
        return (time.time() - self._last_run()) >= 24 * 3600

    # ── 触发 ──

    def maybe_trigger(self) -> dict | None:
        """条件满足则触发 Evolve：阈值达标 + 冷却期过。返回进化结果或 None"""
        if self._evolve_weight() < self._threshold:
            return None
        if not self._cooled_down():
            logger.info("[EvolveTrigger] 冷却期内，跳过触发")
            return None
        history = self._load_experiences()
        logger.info(f"[EvolveTrigger] 触发 L4 Evolve（{len(history)} 条经验）")
        try:
            result = self._runner(history)
        except Exception as e:
            logger.warning(f"[EvolveTrigger] Evolve 执行失败: {e}")
            return None
        self._stamp_last_run()
        # 进化后清空已消费经验，避免下一轮重复回放
        try:
            self._jsonl.unlink(missing_ok=True)
        except OSError:
            pass
        return result

    @staticmethod
    def _default_runner(history: list[dict]) -> dict:
        from agent_core.meta_evolution import MetaEvolution
        return MetaEvolution().run_full_cycle(history)


# ── CommanderV2 接线（方案A：ECO_AUTO_EVOLVE=1 显式启用）──

def mission_hook(summary: dict, tasks: list):
    """供 CommanderV2.execute() 收尾调用。未启用时完全 no-op。"""
    if os.environ.get("ECO_AUTO_EVOLVE", "").strip().lower() not in ("1", "true", "yes"):
        return None
    try:
        trig = EvolveTrigger()
        trig.record_mission(summary, tasks)
        return trig.maybe_trigger()
    except Exception as e:
        logger.warning(f"[EvolveTrigger] mission_hook 异常（不影响主流程）: {e}")
        return None
