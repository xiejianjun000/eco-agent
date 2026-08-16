#!/usr/bin/env python3
"""
agent_core/session_log.py — 不可变会话事件日志（对标 DSH 会话持久化基础设施）

特性:
  - append-only：事件只追加不修改，seq 单调递增
  - 每条事件带 SHA-256 链校验（prev_hash），可整体 verify()
  - 崩溃/截断恢复：尾部损坏行自动截断，前序链完整可用
  - 可重放（replay）与尾部读取（tail），供压缩/审计/恢复消费
  - 存储: memory-tree/data/session_log/<session_id>.jsonl

与既有机制分工:
  - prompt_engine SM3 审计链 → 权限/安全审计（已有）
  - 本模块 → 会话事实流（消息/工具调用/系统事件）的持久化与重放
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from pathlib import Path
from typing import Any
from collections.abc import Iterator

logger = logging.getLogger("eco.session_log")

DATA_DIR = Path(__file__).resolve().parent.parent / "memory-tree" / "data" / "session_log"


class SessionEventLog:
    """单个会话的不可变事件日志。"""

    def __init__(self, session_id: str, base_dir: Path | None = None) -> None:
        self.session_id = session_id
        self.base_dir = Path(base_dir) if base_dir else DATA_DIR
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.base_dir / f"{session_id}.jsonl"
        self._lock = threading.RLock()
        self._head_hash = self._compute_head_hash()

    # ── 追加 ─────────────────────────────────────────────

    def append(self, event_type: str, data: dict[str, Any]) -> int:
        """追加一条事件，返回 seq。event_type 见 SESSION_EVENT_TYPES。"""
        with self._lock:
            seq = self._next_seq()
            event = {
                "seq": seq,
                "time": time.time(),
                "type": event_type,
                "data": data,
            }
            event["prev_hash"] = self._head_hash
            payload = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
            event["hash"] = hashlib.sha256(payload.encode("utf-8")).hexdigest()
            line = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
            with self.path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
                f.flush()
                import os
                os.fsync(f.fileno())
            self._head_hash = event["hash"]
            return seq

    # ── 读取/重放 ─────────────────────────────────────────

    def replay(self) -> Iterator[dict]:
        """按序重放全部完整事件（损坏行处停止）。"""
        with self._lock:
            yield from self._iter_events()

    def tail(self, n: int = 20) -> list[dict]:
        """最近 n 条完整事件。"""
        events = list(self._iter_events())
        return events[-n:]

    def get(self, seq: int) -> dict | None:
        for e in self._iter_events():
            if e["seq"] == seq:
                return e
        return None

    # ── 完整性 ────────────────────────────────────────────

    def verify(self) -> dict:
        """校验整条链：hash 链 + prev_hash 衔接 + seq 连续。"""
        events = []
        prev_hash = ""
        expected_seq = 1
        truncated = 0
        for line in self._raw_lines():
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                truncated += 1
                break  # 尾部截断，停止
            if e.get("seq") != expected_seq:
                return {"ok": False, "error": f"seq 断裂: 期望 {expected_seq} 实得 {e.get('seq')}",
                        "events": len(events)}
            payload = json.dumps({k: e[k] for k in ("seq", "time", "type", "data", "prev_hash")},
                                 ensure_ascii=False, separators=(",", ":"))
            if hashlib.sha256(payload.encode("utf-8")).hexdigest() != e.get("hash"):
                return {"ok": False, "error": f"hash 校验失败 @ seq {e.get('seq')}",
                        "events": len(events)}
            if e.get("prev_hash") != prev_hash:
                return {"ok": False, "error": f"prev_hash 链断裂 @ seq {e.get('seq')}",
                        "events": len(events)}
            prev_hash = e["hash"]
            expected_seq += 1
            events.append(e)
        return {"ok": True, "events": len(events), "truncated": truncated,
                "last_seq": events[-1]["seq"] if events else 0}

    def stats(self) -> dict:
        v = self.verify()
        by_type: dict[str, int] = {}
        for e in self._iter_events():
            by_type[e.get("type", "?")] = by_type.get(e.get("type", "?"), 0) + 1
        v["by_type"] = by_type
        v["size_bytes"] = self.path.stat().st_size if self.path.exists() else 0
        return v

    # ── 内部 ─────────────────────────────────────────────

    def _next_seq(self) -> int:
        events = list(self._iter_events())
        return (events[-1]["seq"] + 1) if events else 1

    def _compute_head_hash(self) -> str:
        events = list(self._iter_events())
        return events[-1]["hash"] if events else ""

    def _raw_lines(self) -> list[str]:
        if not self.path.exists():
            return []
        return self.path.read_text(encoding="utf-8", errors="replace").splitlines()

    def _iter_events(self) -> Iterator[dict]:
        """迭代完整解析成功的事件（损坏行处停止）。"""
        for line in self._raw_lines():
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                break


# 事件类型词汇（声明合并式扩展：插件可 register_event_type 补充）
SESSION_EVENT_TYPES = {
    "user/message": "用户消息",
    "assistant/message": "助手消息",
    "tool/result": "工具执行结果",
    "system/start": "会话开始",
    "system/end": "会话结束",
    "compaction/summary": "上下文压缩摘要",
    "evolution/report": "进化报告落点",
    "memory/consolidation": "记忆固化",
}


def register_event_type(event_type: str, label: str) -> None:
    """扩展事件类型词汇（插件/模块可用）。"""
    SESSION_EVENT_TYPES[event_type] = label


def list_sessions(base_dir: Path | None = None) -> list[dict]:
    base = Path(base_dir) if base_dir else DATA_DIR
    if not base.is_dir():
        return []
    out = []
    for p in sorted(base.glob("*.jsonl")):
        log = SessionEventLog(p.stem, base_dir=base)
        st = log.stats()
        out.append({"session_id": p.stem, **st})
    return out
