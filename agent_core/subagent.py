#!/usr/bin/env python3
"""
agent_core/subagent.py — 通用子代理系统（对标 DSH packages/subagent）

能力对齐 DSH：
  - spawn：发起子代理（前台/后台），后台挂 asyncio.Task
  - fork：携带父会话历史前缀（API history 参数直传）
  - send_message：可延续续聊（idle/done 后可继续同一子代理对话）
  - interrupt：中断运行中的子代理
  - list/get：子代理目录与详情
  - 输出流：trace 事件 + 最终回复按 seq 增量读取（对标 DSH job_output）
  - 持久化：每次生命周期事件写 session_log（SHA-256 链，重启可恢复）

执行复用 server.api.chat._chat_with_codex_loop（法典工具循环 + 纠偏 + 流式），
lazy import 避免 agent_core ↔ server.api 循环依赖。
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
import uuid
from typing import Any

logger = logging.getLogger("eco.subagent")

_SUBAGENT_STATUSES = ("pending", "running", "idle", "done", "failed", "killed")


class Subagent:
    """一个子代理实例：状态 + 会话历史 + 结果 + 输出流。"""

    def __init__(self, prompt: str, parent_history: list[dict] | None = None,
                 model: str = "", label: str = "", parent_id: str | None = None) -> None:
        self.id = uuid.uuid4().hex[:12]
        self.label = label or prompt[:24]
        self.prompt = prompt
        self.parent_history = list(parent_history or [])
        self.parent_id = parent_id
        self.model = model
        self.status = "pending"
        self.created_at = time.time()
        self.started_at: float | None = None
        self.finished_at: float | None = None
        self.result: str | None = None
        self.error: str | None = None
        self.usage: dict = {}
        self.trace: list[dict] = []
        # 输出流（工具轨迹 + 最终回复），供增量读取；seq 从 0 递增
        self.output: list[dict] = []
        self._output_seq = 0
        # 自身会话（send_message 续聊时追加），执行时 = parent_history + prompt
        self.messages: list[dict] = list(self.parent_history)
        self._task: asyncio.Task | None = None
        self._lock = threading.RLock()
        self._cancel = threading.Event()

    # ── 状态 ─────────────────────────────────────────────

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "id": self.id,
                "label": self.label,
                "status": self.status,
                "parent_id": self.parent_id,
                "model": self.model or "default",
                "created_at": self.created_at,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "duration_ms": int(((self.finished_at or time.time())
                                    - (self.started_at or self.created_at)) * 1000),
                "turns": len(self.messages),
                "usage": dict(self.usage),
                "trace_events": len(self.trace),
                "output_seq": self._output_seq,
                "result": (self.result or "")[:2000] if self.status in ("done", "idle") else None,
                "error": self.error,
            }

    # ── 输出流 ───────────────────────────────────────────

    def _emit(self, kind: str, payload: dict) -> None:
        with self._lock:
            self._output_seq += 1
            ev = {"seq": self._output_seq, "time": time.time(),
                  "kind": kind, **payload}
            self.output.append(ev)
            if len(self.output) > 2000:  # 输出上限：防止无界增长
                self.output = self.output[-2000:]

    def read_output(self, since_seq: int = 0) -> tuple[list[dict], int]:
        """增量读取输出（对标 job_output）：返回 (新事件, 当前 seq)。"""
        with self._lock:
            new = [e for e in self.output if e["seq"] > since_seq]
            return new, self._output_seq

    # ── 执行 ─────────────────────────────────────────────

    def run_async(self, loop: asyncio.AbstractEventLoop | None = None) -> asyncio.Task:
        """以 asyncio.Task 后台运行（在调用方的事件循环上）。"""

        def _consume(task: asyncio.Task) -> None:
            try:
                if not task.cancelled():
                    task.exception()  # 消费异常，避免 'never retrieved' 警告
            except asyncio.CancelledError:
                pass

        self._task = asyncio.ensure_future(self._run(), loop=loop)
        self._task.add_done_callback(_consume)
        return self._task

    async def _run(self) -> None:
        from agent_core.llm_client import get_default_client
        from agent_core.session_log import SessionEventLog
        from server.api.chat import _build_messages, _chat_with_codex_loop

        with self._lock:
            self.status = "running"
            self.started_at = time.time()
        self._emit("status", {"status": "running"})
        try:
            slog = SessionEventLog(f"subagent/{self.id}")
            slog.append("system/start", {"label": self.label, "parent_id": self.parent_id,
                                         "prompt": self.prompt[:500]})
            client = get_default_client()
            messages = _build_messages(self.prompt, self.parent_history)
            reply, trace, usage, first_llm_ms, first_token_ms = await _chat_with_codex_loop(
                client, messages, self.model)
            for ev in trace:
                if ev.get("type") in ("think", "tool", "correction", "answer"):
                    self.trace.append(ev)
                    self._emit("trace", {"event": ev})
            with self._lock:
                self.result = reply
                self.usage = dict(usage)
                self.status = "done"
                self.finished_at = time.time()
                # 自身会话供续聊：保留构建出的 messages（含 system 与工具回填）
                self.messages = list(messages)
            self._emit("done", {"result": reply[:2000]})
            slog.append("assistant/message", {"reply": reply[:2000],
                                              "usage": dict(usage)})
        except asyncio.CancelledError:
            with self._lock:
                self.status = "killed"
                self.finished_at = time.time()
            self._emit("status", {"status": "killed"})
            if "slog" in locals():
                slog.append("system/end", {"status": "killed"})
            raise
        except Exception as e:  # noqa: BLE001 — 子代理失败不拖垮主会话
            logger.exception("subagent %s failed", self.id)
            with self._lock:
                self.status = "failed"
                self.error = f"{type(e).__name__}: {e}"
                self.finished_at = time.time()
            self._emit("failed", {"error": self.error})
            if "slog" in locals():
                slog.append("system/end", {"status": "failed", "error": self.error})

    async def continue_with(self, message: str) -> None:
        """send_message 续聊：在既有会话上追加消息继续执行（continuable）。"""
        from agent_core.llm_client import get_default_client
        from server.api.chat import _chat_with_codex_loop

        with self._lock:
            if self.status in ("running", "pending"):
                raise RuntimeError(f"子代理正在运行（{self.status}），不可续聊")
            self.messages.append({"role": "user", "content": message})
            self.status = "running"
            self.started_at = time.time()
        self._emit("status", {"status": "running"})
        try:
            client = get_default_client()
            reply, trace, usage, _, _ = await _chat_with_codex_loop(
                client, list(self.messages), self.model)
            for ev in trace:
                if ev.get("type") in ("think", "tool", "correction", "answer"):
                    self.trace.append(ev)
                    self._emit("trace", {"event": ev})
            with self._lock:
                self.messages.append({"role": "assistant", "content": reply})
                self.result = reply
                self.usage = dict(usage)
                self.status = "idle"
                self.finished_at = time.time()
            self._emit("done", {"result": reply[:2000]})
        except asyncio.CancelledError:
            with self._lock:
                self.status = "killed"
                self.finished_at = time.time()
            self._emit("status", {"status": "killed"})
            raise
        except Exception as e:  # noqa: BLE001
            logger.exception("subagent %s continue failed", self.id)
            with self._lock:
                self.status = "failed"
                self.error = f"{type(e).__name__}: {e}"
                self.finished_at = time.time()
            self._emit("failed", {"error": self.error})

    def interrupt(self) -> bool:
        """中断运行中的子代理（asyncio.Task.cancel）。"""
        with self._lock:
            if self._task is None or self.status not in ("running", "pending"):
                return False
            task = self._task
        task.cancel()
        return True


class SubagentRegistry:
    """子代理注册表（单例）：start/list/get/send_message/interrupt。"""

    def __init__(self) -> None:
        self._agents: dict[str, Subagent] = {}
        self._lock = threading.RLock()

    def start(self, prompt: str, history: list[dict] | None = None,
              model: str = "", background: bool = True,
              label: str = "", parent_id: str | None = None) -> dict:
        """发起子代理。background=False 时同步等待结果（API 层用）。"""
        agent = Subagent(prompt, history, model=model, label=label, parent_id=parent_id)
        with self._lock:
            self._agents[agent.id] = agent
        if background:
            agent.run_async()
        return agent.snapshot()

    def get(self, agent_id: str) -> Subagent | None:
        with self._lock:
            return self._agents.get(agent_id)

    def list(self) -> list[dict]:
        with self._lock:
            return [a.snapshot() for a in sorted(
                self._agents.values(), key=lambda a: -a.created_at)]

    def read_output(self, agent_id: str, since_seq: int = 0) -> tuple[list[dict], int] | None:
        agent = self.get(agent_id)
        if agent is None:
            return None
        return agent.read_output(since_seq)

    def send_message(self, agent_id: str, message: str) -> dict:
        agent = self.get(agent_id)
        if agent is None:
            raise KeyError(f"子代理不存在: {agent_id}")
        # 同步检查状态（不可在协程内才发现冲突）
        if agent.status in ("running", "pending"):
            raise RuntimeError(f"子代理正在运行（{agent.status}），不可续聊")
        asyncio.ensure_future(agent.continue_with(message))
        return {"id": agent_id, "status": "running"}

    def interrupt(self, agent_id: str) -> bool:
        agent = self.get(agent_id)
        if agent is None:
            return False
        return agent.interrupt()

    def stats(self) -> dict:
        with self._lock:
            by_status: dict[str, int] = {}
            for a in self._agents.values():
                by_status[a.status] = by_status.get(a.status, 0) + 1
            return {"agents": len(self._agents), "by_status": by_status}


_registry: SubagentRegistry | None = None
_registry_lock = threading.Lock()


def get_subagent_registry() -> SubagentRegistry:
    """进程级单例注册表。"""
    global _registry
    with _registry_lock:
        if _registry is None:
            _registry = SubagentRegistry()
        return _registry
