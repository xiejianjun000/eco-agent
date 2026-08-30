#!/usr/bin/env python3
"""
agent_core/goal.py — 跨轮持久化目标系统（对标 DSH packages/goal）

目标以 jsonl 持久化（memory-tree/data/goals.jsonl），状态机：
  active → armed 续轮（rounds < max_goal_rounds 时每轮完成后自动发起下一轮）
        → completed（手动/判定达成）| blocked（达到轮上限或阻塞条件）
        → paused（暂停，resume 重新武装）

执行：goal 绑定一个后台子代理（复用 agent_core.subagent），
每轮执行完成后把结果摘要作为下一轮上下文自动延续（DSH goal-round-driver 语义的
简化版：驱动点从 'agent idle' 改为 '子代理完成回调'）。

与 DSH 的差异（如实声明）：无事件溯源快照（直接 jsonl 全量读写），
无 LLM 自动达成判定（completed 由用户/调用方标记，或由确定性完成信号
`✅/已完成` 且无待续/失败信号触发完成即停；轮上限兜底自动 blocked）。
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger("eco.goal")

DATA_DIR = Path(__file__).resolve().parent.parent / "memory-tree" / "data"
GOALS_FILE = DATA_DIR / "goals.jsonl"

GOAL_STATUSES = ("active", "paused", "completed", "blocked")


class GoalStore:
    """目标仓库：jsonl 持久化 + 自动延续驱动。"""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else GOALS_FILE
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._goals: dict[str, dict] = self._load()

    def _load(self) -> dict[str, dict]:
        out: dict[str, dict] = {}
        if not self.path.exists():
            return out
        for line in self.path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                g = json.loads(line)
                out[g["id"]] = g
            except json.JSONDecodeError:
                continue
        return out

    def _save(self) -> None:
        with self.path.open("w", encoding="utf-8") as f:
            for g in self._goals.values():
                f.write(json.dumps(g, ensure_ascii=False) + "\n")

    # ── CRUD ────────────────────────────────────────────

    def create(self, objective: str, max_goal_rounds: int = 10,
               auto_run: bool = False, context: str = "") -> dict:
        """创建目标。auto_run=True 时立即以后台子代理发起首轮。"""
        goal = {
            "id": uuid.uuid4().hex[:12],
            "objective": objective,
            "context": context,
            "max_goal_rounds": max_goal_rounds,
            "status": "active",
            "rounds": 0,
            "created_at": time.time(),
            "updated_at": time.time(),
            "last_result": "",
            "history": [],
            "armed": auto_run,
            "blocked_reason": "",
        }
        with self._lock:
            self._goals[goal["id"]] = goal
            self._save()
        if auto_run:
            self.run_next_round(goal["id"])
        return self.get(goal["id"]) or goal

    def get(self, goal_id: str) -> dict | None:
        with self._lock:
            g = self._goals.get(goal_id)
            return dict(g) if g else None

    def list(self) -> list[dict]:
        with self._lock:
            return [dict(g) for g in sorted(
                self._goals.values(), key=lambda g: -g["created_at"])]

    def _update(self, goal_id: str, mutate) -> dict | None:
        with self._lock:
            g = self._goals.get(goal_id)
            if g is None:
                return None
            mutate(g)
            g["updated_at"] = time.time()
            self._save()
            return dict(g)

    # ── 状态操作 ────────────────────────────────────────

    def pause(self, goal_id: str) -> dict | None:
        def m(g):
            g["status"] = "paused"
            g["armed"] = False
        return self._update(goal_id, m)

    def resume(self, goal_id: str) -> dict | None:
        """重新武装：armed 后由 run_next_round 驱动。"""
        def m(g):
            g["status"] = "active"
            g["armed"] = True
        goal = self._update(goal_id, m)
        if goal is not None:
            self.run_next_round(goal_id)
        return goal

    def complete(self, goal_id: str, note: str = "") -> dict | None:
        def m(g):
            g["status"] = "completed"
            g["armed"] = False
            if note:
                g["history"].append({"time": time.time(), "type": "complete", "note": note})
        return self._update(goal_id, m)

    def block(self, goal_id: str, reason: str) -> dict | None:
        def m(g):
            g["status"] = "blocked"
            g["armed"] = False
            g["blocked_reason"] = reason
        return self._update(goal_id, m)

    def delete(self, goal_id: str) -> bool:
        """删除目标（清理已完成/阻塞/测试的陈旧目标）。"""
        with self._lock:
            if goal_id not in self._goals:
                return False
            del self._goals[goal_id]
            self._save()
            return True

    # ── 自动延续驱动 ────────────────────────────────────

    def run_next_round(self, goal_id: str) -> dict:
        """发起下一轮：后台子代理执行目标（DSH goal-round-driver 简化版）。

        执行完成后回调 _on_round_done：rounds+1；若 armed 且未达轮上限，
        把结果摘要并入 context 自动发起下一轮；达上限则 blocked(round-limit)。
        """
        from agent_core.subagent import get_subagent_registry

        goal = self.get(goal_id)
        if goal is None:
            return {"ok": False, "error": f"目标不存在: {goal_id}"}
        if goal["status"] != "active":
            return {"ok": False, "error": f"目标不可执行（status={goal['status']}）"}
        if goal["rounds"] >= goal["max_goal_rounds"]:
            self.block(goal_id, "round-limit")
            return {"ok": False, "error": "已达轮次上限，目标已 blocked"}
        if not goal["armed"]:
            return {"ok": False, "error": "目标未武装（pause 状态），resume 后执行"}

        prompt = goal["objective"]
        if goal["context"]:
            prompt = f"{prompt}\n\n【此前轮次上下文】\n{goal['context'][-4000:]}"

        def _on_done(agent) -> None:
            self._on_round_done(goal_id, agent)

        registry = get_subagent_registry()
        snap = registry.start(prompt, background=True, label=f"goal:{goal['objective'][:16]}")
        agent = registry.get(snap["id"])
        if agent is not None:
            # 子代理完成后回调（不侵入 subagent 模块：轮询注册完成状态）
            import asyncio

            async def _watch() -> None:
                while agent.status in ("pending", "running"):
                    await asyncio.sleep(1.5)
                _on_done(agent)

            try:
                asyncio.ensure_future(_watch())
            except RuntimeError:
                # 无事件循环（CLI/测试环境）：同步等待
                while agent.status in ("pending", "running"):
                    time.sleep(1.5)
                _on_done(agent)
        return {"ok": True, "goal_id": goal_id, "subagent_id": snap["id"],
                "round": goal["rounds"] + 1}

    def _notify_event(self, goal_id: str, event: str, detail: str) -> None:
        """目标事件通知落盘（ECO_DIR/goal_notifications.jsonl）——
        Web 端 /api/v1/goals/events 轮询展示，后台任务完成可自动可见。"""
        try:
            base = Path(os.environ.get("ECO_DIR") or Path.home() / ".eco")
            path = base / "goal_notifications.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": time.time(), "goal_id": goal_id,
                                    "event": event, "detail": detail[:500]},
                                   ensure_ascii=False) + "\n")
        except Exception:
            pass

    def _on_round_done(self, goal_id: str, agent) -> None:
        result = (agent.result or agent.error or "")[:2000]
        goal = self.get(goal_id)
        if goal is None or goal["status"] != "active":
            return
        rounds = goal["rounds"] + 1

        def m(g):
            g["rounds"] = rounds
            g["last_result"] = result
            g["history"].append({"time": time.time(), "round": rounds,
                                 "result": result[:500]})
            if agent.status == "done":
                if _looks_complete(result):
                    # 完成即停：结果带强完成信号（✅/已完成）且无待续/失败信号 → completed
                    g["status"] = "completed"
                    g["armed"] = False
                elif rounds >= g["max_goal_rounds"]:
                    g["status"] = "blocked"
                    g["armed"] = False
                    g["blocked_reason"] = "round-limit"
                    g["context"] = (g.get("context", "") + f"\n[第{rounds}轮结果] {result}")[-8000:]
                else:
                    g["context"] = (g.get("context", "") + f"\n[第{rounds}轮结果] {result}")[-8000:]
                    g["armed"] = True
            else:
                # 失败：阻塞并记录
                g["status"] = "blocked"
                g["armed"] = False
                g["blocked_reason"] = f"round {rounds} failed: {agent.error or agent.status}"
        self._update(goal_id, m)
        goal = self.get(goal_id)
        if goal:
            self._notify_event(
                goal_id,
                "completed" if goal["status"] == "completed" else
                ("blocked" if goal["status"] == "blocked" else "round_done"),
                f"第{rounds}轮 {goal['status']}: {result[:200]}")
        if goal and goal["armed"] and goal["status"] == "active":
            logger.info("goal %s 第 %s 轮完成，自动发起下一轮", goal_id, rounds)
            self.run_next_round(goal_id)

    def stats(self) -> dict:
        with self._lock:
            by_status: dict[str, int] = {}
            for g in self._goals.values():
                by_status[g["status"]] = by_status.get(g["status"], 0) + 1
            return {"goals": len(self._goals), "by_status": by_status}


_COMPLETE_SIGNAL = re.compile(r"✅|已完成|完成标准已达成|任务完成")
_INCOMPLETE_SIGNAL = re.compile(
    r"要我继续|需要我|待确认|还需|下一步|是否继续|请确认|继续查|尚未完成|未完成|继续执行")
_FAIL_SIGNAL = re.compile(r"\[eco-server\]|Traceback|失败|报错", re.I)


def _looks_complete(result: str) -> bool:
    """完成即停判定：子代理结果带强完成信号（✅/已完成）且无半途/待续/失败信号时视为达成。

    保守策略：宁可多跑一轮也不误判完成——只要出现"还需/待确认/要我继续"等未完信号
    或失败信号，就继续到轮上限（保留原 round-limit 兜底），避免简单任务空转满轮。
    """
    r = (result or "").strip()
    if not r:
        return False
    if _INCOMPLETE_SIGNAL.search(r):
        return False
    if _FAIL_SIGNAL.search(r):
        return False
    return bool(_COMPLETE_SIGNAL.search(r))


_store: GoalStore | None = None
_store_lock = threading.Lock()


def get_goal_store() -> GoalStore:
    global _store
    with _store_lock:
        if _store is None:
            _store = GoalStore()
        return _store
