#!/usr/bin/env python3
"""
agent_core/cordis_plugins/skill_hatcher.py — 自主技能孵化插件
====================================================================
对标 Hermes「复杂任务完成后自动沉淀成技能」+ eco G7「同类操作 3 次→正式 Skill」。

skill_system.py 的 SkillRegistry + AutoLearnEngine（skill 注册/持久化/自动学习）
此前已实现但无调用方。本插件通电：
  - 监听同类「工具组合」使用频率（持久化计数）
  - 同一工具组合使用 ≥3 次 → AutoLearnEngine.learn_from_task 孵化成 Skill
    （落 skills/<name>.md + skill_registry.json）
  - provide skill_hatcher 服务，供 chat 通道 turn 结束时 observe

配置（eco.cordis.yml）：
  - plugin: agent_core.cordis_plugins.skill_hatcher
    config: { hatch_threshold: 3, min_tools: 2 }
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

logger = logging.getLogger("eco.cordis.skill_hatcher")

_COUNTER_FILE = Path(__file__).resolve().parent.parent.parent / "memory-tree" / "data" / "skill_hatch_counter.json"


class Hatcher:
    """技能孵化器：同类工具组合 ≥N 次 → 提炼为 Skill。"""

    def __init__(self, threshold: int, min_tools: int):
        self._threshold = threshold
        self._min_tools = min_tools
        self._lock = threading.Lock()
        self._counter: dict[str, int] = {}
        self._load()
        # 惰性初始化（首次 observe 时），避免插件加载即触发热路径
        self._engine = None

    def _engine_ready(self):
        if self._engine is None:
            from agent_core.skill_system import SkillRegistry, AutoLearnEngine

            self._engine = AutoLearnEngine(SkillRegistry())
        return self._engine

    def _load(self) -> None:
        if _COUNTER_FILE.exists():
            try:
                self._counter = json.loads(_COUNTER_FILE.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._counter = {}

    def _save(self) -> None:
        try:
            _COUNTER_FILE.parent.mkdir(parents=True, exist_ok=True)
            _COUNTER_FILE.write_text(json.dumps(self._counter, ensure_ascii=False), encoding="utf-8")
        except OSError:  # pragma: no cover
            pass

    def observe(self, task_desc: str, tools: list[str], reply: str) -> str | None:
        """每次任务完成调用：统计工具组合频率，达阈值孵化技能。
        返回孵化出的 skill_id，未孵化返回 None。"""
        tools = [t for t in (tools or []) if t]
        if len(tools) < self._min_tools:
            return None
        sig = "|".join(sorted(set(tools)))
        with self._lock:
            self._counter[sig] = self._counter.get(sig, 0) + 1
            self._save()
            if self._counter[sig] < self._threshold:
                return None
            # 达阈值：孵化后重置计数，避免重复孵化同一组合
            self._counter[sig] = 0
            self._save()
        engine = self._engine_ready()
        skill_id = engine.learn_from_task(
            task_desc=(task_desc or "")[:60],
            task_steps=tools[:6],
            task_output=(reply or "")[:200],
            score=3.0,
            min_steps=self._min_tools,  # 孵化门槛与 Hatcher.min_tools 一致
        )
        if skill_id:
            logger.info("[skill_hatcher] 孵化技能 %s（工具组合: %s，第 %d 次触发）",
                        skill_id, sig, self._threshold)
        return skill_id

    def stats(self) -> dict:
        return {"threshold": self._threshold, "min_tools": self._min_tools,
                "counter": dict(self._counter)}


def apply(ctx, config: dict | None = None) -> None:
    """组合装配入口：通电技能孵化器（幂等）。"""
    config = config or {}
    threshold = int(config.get("hatch_threshold", 3))
    min_tools = int(config.get("min_tools", 3))
    hatcher = Hatcher(threshold=threshold, min_tools=min_tools)
    ctx.provide("skill_hatcher", hatcher)
    logger.info("[skill_hatcher] 通电: threshold=%d min_tools=%d", threshold, min_tools)
