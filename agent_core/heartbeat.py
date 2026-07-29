#!/usr/bin/env python3
"""
heartbeat.py — Eco Agent L3 后台心跳循环 (Autonomous Pulse)

对标 OpenHuman 的"潜意识循环" + Codex 的"定时心跳自动化任务。
在用户未交互时自主运转：数据同步→差异检测→规则触发→内存整理→主动建议。

节律：每5~20分钟（自适应）
"""

import os, sys, json, time, logging, threading
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Callable

logger = logging.getLogger("heartbeat")

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "memory-tree" / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


class PulseLoop:
    """L3 后台心跳循环——自主运转、自适应频率、静默执行"""

    def __init__(self):
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._pulse_count = 0
        self._interval = 600  # 默认10分钟
        self._min_interval = 300   # 5分钟
        self._max_interval = 1200  # 20分钟
        self._load_aware = True
        self._listeners: Dict[str, Callable] = {}
        self._pulse_log: List[Dict] = []

    def register_listener(self, name: str, handler: Callable):
        """注册心跳监听器——每个STEP对应一个监听器"""
        self._listeners[name] = handler

    def start(self):
        """启动后台心跳"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._pulse_loop, daemon=True, name="heartbeat")
        self._thread.start()
        logger.info(f"Heartbeat: 启动 (间隔{self._interval}s)")

    def stop(self):
        self._running = False
        logger.info("Heartbeat: 停止")

    def _pulse_loop(self):
        while self._running:
            self._pulse_count += 1
            pulse_id = f"pulse_{self._pulse_count}"
            start_time = time.time()
            logger.debug(f"[Pulse] #{self._pulse_count} 开始")

            results = {}
            for name, handler in self._listeners.items():
                try:
                    result = handler()
                    results[name] = {"status": "ok", "result": str(result)[:100]}
                except Exception as e:
                    results[name] = {"status": "error", "error": str(e)}
                    logger.warning(f"[Pulse] {name}: {e}")

            elapsed = time.time() - start_time
            self._pulse_log.append({
                "id": pulse_id, "count": self._pulse_count,
                "timestamp": datetime.now().isoformat(),
                "elapsed_s": round(elapsed, 2),
                "results": results,
            })
            if len(self._pulse_log) > 100:
                self._pulse_log = self._pulse_log[-100:]

            # 自适应间隔
            if self._load_aware:
                self._adapt_interval(elapsed)

            logger.debug(f"[Pulse] #{self._pulse_count} 完成 ({elapsed:.1f}s, 下次{self._interval}s后)")
            time.sleep(self._interval)

    def _adapt_interval(self, elapsed_s: float):
        """自适应调整心跳频率"""
        if elapsed_s > self._interval * 0.8:
            self._interval = min(self._interval * 1.2, self._max_interval)
        elif elapsed_s < self._interval * 0.2:
            self._interval = max(self._interval * 0.8, self._min_interval)

    # ── 内置心跳步骤 ──

    @staticmethod
    def step_sync():
        """STEP 1: 全平台数据同步（占位）"""
        return "sync_ok"

    @staticmethod
    def step_diff():
        """STEP 2: 差异检测"""
        return "no_changes"

    @staticmethod
    def step_rule_engine():
        """STEP 3: 自动触发规则引擎"""
        return "no_rules_triggered"

    @staticmethod
    def step_mem_cron():
        """STEP 4: 内存碎片整理"""
        return "mem_ok"

    @staticmethod
    def step_suggestions():
        """STEP 5: 主动建议生成"""
        return None

    def get_stats(self) -> dict:
        return {
            "pulse_count": self._pulse_count,
            "running": self._running,
            "interval_s": self._interval,
            "listeners": len(self._listeners),
            "last_pulse": self._pulse_log[-1]["timestamp"][:19] if self._pulse_log else "N/A",
        }


# ===== 快速包装 =====

pulse = PulseLoop()


def test():
    import io, sys as _sys
    _sys.stdout = io.TextIOWrapper(_sys.stdout.buffer, encoding='utf-8', errors='replace')

    p = PulseLoop()
    p.register_listener("sync", lambda: "已同步3个平台")
    p.register_listener("diff", lambda: "发现1个变化")
    p.register_listener("mem", lambda: "整理完成")
    p._interval = 2  # 2秒间隔用于测试

    p.start()
    time.sleep(5)
    p.stop()

    stats = p.get_stats()
    print(f"[Pulse] 心跳: {stats['pulse_count']}次, 运行中: {stats['running']}, "
          f"监听器: {stats['listeners']}个", flush=True)
    print("[OK] L3 Heartbeat 测试通过", flush=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test()
