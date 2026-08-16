#!/usr/bin/env python3
"""
agent_core/cordis_plugins/subagent_cleaner.py — 子代理定期清理插件（演示）

对标 DSH 插件语义：
  - inject 声明硬依赖 subagents 服务
  - ctx.set_interval 定时清理已结束（done/failed/killed/idle）超过 TTL 的子代理
  - 副作用随插件卸载自动回收

配置（eco.cordis.yml）：
  - plugin: agent_core.cordis_plugins.subagent_cleaner
    config: {ttl_seconds: 1800, interval_seconds: 300}
    inject: [subagents]
"""

from __future__ import annotations

import logging
import time

logger = logging.getLogger("eco.plugin.subagent_cleaner")


class SubagentCleaner:
    inject = ["subagents"]

    def __init__(self) -> None:
        self.cleaned = 0

    def apply(self, ctx, config: dict) -> None:
        ttl = float(config.get("ttl_seconds", 1800))
        interval = float(config.get("interval_seconds", 300))

        def _clean() -> None:
            registry = ctx.get("subagents")
            if registry is None:
                return
            now = time.time()
            for agent in list(registry._agents.values()):  # noqa: SLF001
                if agent.status in ("done", "failed", "killed", "idle"):
                    if now - (agent.finished_at or agent.created_at) > ttl:
                        with registry._lock:  # noqa: SLF001
                            registry._agents.pop(agent.id, None)  # noqa: SLF001
                        self.cleaned += 1
                        logger.info("subagent_cleaner 清理过期子代理 %s", agent.id)

        ctx.set_interval(_clean, interval, label="subagent_cleaner")
        logger.info("subagent_cleaner 已启用: ttl=%ss interval=%ss", ttl, interval)
