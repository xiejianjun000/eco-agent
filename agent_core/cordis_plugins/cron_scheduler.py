#!/usr/bin/env python3
"""
agent_core/cordis_plugins/cron_scheduler.py — 内置 Cron 定时调度插件
====================================================================
对标 DSH「一切皆插件」：把 scheduler.py 的 CronScheduler（自然语言→cron→
后台线程调度）从"有代码没装配"通电为组合装配的一个 plugin row。

职责：
  - 启动 CronScheduler 后台线程（30s 检查间隔，幂等）
  - provide cron_scheduler 服务（供 chat 工具 / subagent 反查）
  - 注册默认 nudge 处理器：定时任务触发时写提醒到 scheduler_nudges.jsonl
  - 卸载时停止线程（ctx.effect 回收）

配置（eco.cordis.yml）：
  - plugin: agent_core.cordis_plugins.cron_scheduler
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

logger = logging.getLogger("eco.cordis.cron_scheduler")

_NUDGES_FILE = Path(__file__).resolve().parent.parent.parent / "memory-tree" / "data" / "scheduler_nudges.jsonl"


def _nudge_handler() -> str:
    """默认任务处理器：定时任务触发时写一条提醒（供后续对话注入/展示）。"""
    try:
        _NUDGES_FILE.parent.mkdir(parents=True, exist_ok=True)
        with _NUDGES_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.time(), "task": "定时任务触发"}, ensure_ascii=False) + "\n")
    except OSError:  # pragma: no cover
        pass
    return "已触发并记录提醒"


def apply(ctx, config: dict | None = None) -> None:
    """组合装配入口：通电 CronScheduler（幂等）。"""
    from agent_core.scheduler import scheduler

    config = config or {}
    scheduler.register_handler("nudge", _nudge_handler)
    scheduler.start()  # 幂等：已 running 直接返回

    # 提供服务，供 chat 工具链 / 外部消费方反查
    ctx.provide("cron_scheduler", scheduler)

    # 卸载回收：停止调度线程
    ctx.effect(lambda: scheduler.stop(), label="cron_scheduler.stop")

    logger.info("[cron_scheduler] 通电: running=%s, 任务数=%d",
                scheduler._running, len(scheduler.list_jobs()))  # noqa: SLF001
