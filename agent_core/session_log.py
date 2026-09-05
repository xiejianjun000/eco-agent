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
import os
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

logger = logging.getLogger("eco.session_log")

DATA_DIR = Path(__file__).resolve().parent.parent / "memory-tree" / "data" / "session_log"


class SessionEventLog:
    """单个会话的不可变事件日志。"""

    # 批写自动 flush 间隔（秒）：None 或 <=0 = 关闭（手动 flush，默认）；
    # >0 = append_buffered 后经防抖定时器自动 flush（WriteBehind 语义）。
    BATCH_FLUSH_INTERVAL: float | None = None

    def __init__(self, session_id: str, base_dir: Path | None = None) -> None:
        self.session_id = session_id
        self.base_dir = Path(base_dir) if base_dir else DATA_DIR
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.base_dir / f"{session_id}.jsonl"
        self._lock = threading.RLock()
        self._head_hash = self._compute_head_hash()
        # WriteBehind 缓冲：append_buffered 事件暂存内存，flush() 批量落盘 + fsync
        self._buffer: list[dict] = []
        self._flush_timer: threading.Timer | None = None

    # ── 追加 ─────────────────────────────────────────────

    def append(self, event_type: str, data: dict[str, Any]) -> int:
        """追加一条事件，返回 seq。event_type 见 SESSION_EVENT_TYPES。
        支持嵌套 session_id（如 'subagent/xxx'）：自动创建父目录。

        默认行为不变：即时写盘 + fsync；若存在未落盘的缓冲事件，先冲刷缓冲，
        保证磁盘 hash 链顺序不被 WriteBehind 缓冲打乱。"""
        with self._lock:
            self.flush()
            seq = self._next_seq()
            event = self._build_event(event_type, data, seq, self._head_hash)
            line = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
                f.flush()
                os.fsync(f.fileno())
            self._head_hash = event["hash"]
            return seq

    # ── WriteBehind 缓冲批写 ─────────────────────────────

    def append_buffered(self, event_type: str, data: dict[str, Any]) -> int:
        """WriteBehind 语义：事件只进内存队列（不落盘、不 fsync），
        由后续 flush() 一次性批量写入并 fsync。返回 seq。

        seq / prev_hash 链在内存中即时衔接，flush() 后与磁盘链无缝续接；
        与 append() 混用时 append() 会先冲刷缓冲，保证链序正确。
        BATCH_FLUSH_INTERVAL > 0 时自动调度防抖 flush（可选开关，默认关闭）。"""
        with self._lock:
            if self._buffer:
                prev_seq = self._buffer[-1]["seq"]
                prev_hash = self._buffer[-1]["hash"]
            else:
                prev_seq = self._next_seq() - 1
                prev_hash = self._head_hash
            seq = prev_seq + 1
            event = self._build_event(event_type, data, seq, prev_hash)
            self._buffer.append(event)
            if self.BATCH_FLUSH_INTERVAL is not None and self.BATCH_FLUSH_INTERVAL > 0:
                self._schedule_auto_flush()
            return seq

    def flush(self) -> int:
        """把内存缓冲一次性批量写入磁盘并 fsync，返回落盘事件数。空缓冲为无操作，幂等。"""
        with self._lock:
            self._cancel_flush_timer()
            if not self._buffer:
                return 0
            self.path.parent.mkdir(parents=True, exist_ok=True)
            lines = [json.dumps(e, ensure_ascii=False, separators=(",", ":")) + "\n" for e in self._buffer]
            with self.path.open("a", encoding="utf-8") as f:
                f.writelines(lines)
                f.flush()
                os.fsync(f.fileno())
            self._head_hash = self._buffer[-1]["hash"]
            n = len(self._buffer)
            self._buffer = []
            return n

    def buffered_count(self) -> int:
        """当前内存缓冲中待落盘的事件数（诊断用）。"""
        with self._lock:
            return len(self._buffer)

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
                return {"ok": False, "error": f"seq 断裂: 期望 {expected_seq} 实得 {e.get('seq')}", "events": len(events)}
            payload = json.dumps(
                {k: e[k] for k in ("seq", "time", "type", "data", "prev_hash")}, ensure_ascii=False, separators=(",", ":")
            )
            if hashlib.sha256(payload.encode("utf-8")).hexdigest() != e.get("hash"):
                return {"ok": False, "error": f"hash 校验失败 @ seq {e.get('seq')}", "events": len(events)}
            if e.get("prev_hash") != prev_hash:
                return {"ok": False, "error": f"prev_hash 链断裂 @ seq {e.get('seq')}", "events": len(events)}
            prev_hash = e["hash"]
            expected_seq += 1
            events.append(e)
        return {"ok": True, "events": len(events), "truncated": truncated, "last_seq": events[-1]["seq"] if events else 0}

    def repair_torn_tail(self) -> dict:
        """断尾修复（对标 DSH torn-tail repair）：崩溃可能留下半行/损坏行，
        截断到最后一个完整事件并追加 system/repair 审计事件。幂等。"""
        lines = self._raw_lines()
        good: list[str] = []
        broken = False
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                json.loads(line)
                good.append(line)
            except json.JSONDecodeError:
                broken = True
                break  # 断尾起于此，其后全部丢弃
        if not broken:
            return {"repaired": False, "note": "no torn tail"}
        with self._lock:
            self.path.write_text("\n".join(good) + ("\n" if good else ""), encoding="utf-8")
        self.append("system/repair", {"dropped_lines": len(lines) - len(good), "note": "torn tail repaired"})
        return {"repaired": True, "dropped_lines": len(lines) - len(good), "last_seq": self.verify().get("last_seq", 0)}

    def repair_seq_gap(self) -> dict:
        """seq 跳变修复（对标 DSH 尾部损坏恢复）：扫描到第一个 seq 不连续
        的位置，截断其后全部行并追加 system/repair 审计事件。幂等。
        中部挖洞（跳变后又恢复连续）不修复——那是篡改信号，保持 fail-closed。"""
        lines = self._raw_lines()
        expected = 1
        cut_at = None
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                cut_at = i
                break
            if e.get("seq") != expected:
                cut_at = i
                break
            expected += 1
        if cut_at is None:
            return {"repaired": False, "note": "no seq gap"}
        good = [line for line in lines[:cut_at] if line.strip()]
        with self._lock:
            self.path.write_text("\n".join(good) + ("\n" if good else ""), encoding="utf-8")
        self.append("system/repair", {"dropped_lines": len(lines) - len(good), "note": "seq gap repaired (tail truncated)"})
        return {"repaired": True, "dropped_lines": len(lines) - len(good), "last_seq": expected - 1}

    def durable(self) -> tuple[bool, dict]:
        """持久性检查：链完整（无断尾、无 hash/seq 断裂）即可安全 checkpoint。

        校验前先 flush 内存缓冲（保证 WriteBehind 队列先落盘再校验），
        因此 checkpoint_policy.durable_guard 无需感知缓冲对象即可 fail-closed。"""
        self.flush()
        v = self.verify()
        return bool(v.get("ok") is True and v.get("truncated", 0) == 0), v

    def stats(self) -> dict:
        v = self.verify()
        by_type: dict[str, int] = {}
        for e in self._iter_events():
            by_type[e.get("type", "?")] = by_type.get(e.get("type", "?"), 0) + 1
        v["by_type"] = by_type
        v["size_bytes"] = self.path.stat().st_size if self.path.exists() else 0
        return v

    # ── 内部 ─────────────────────────────────────────────

    def _build_event(self, event_type: str, data: dict[str, Any], seq: int, prev_hash: str) -> dict:
        """构造带 hash 的完整事件（seq/time/type/data/prev_hash 五元组签名）。"""
        event = {
            "seq": seq,
            "time": time.time(),
            "type": event_type,
            "data": data,
            "prev_hash": prev_hash,
        }
        payload = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
        event["hash"] = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return event

    def _schedule_auto_flush(self) -> None:
        """防抖定时 flush：每次 append_buffered 重置计时器（单一定时器，默认关闭）。"""
        if self._flush_timer is not None:
            self._flush_timer.cancel()
        self._flush_timer = threading.Timer(self.BATCH_FLUSH_INTERVAL, self.flush)
        self._flush_timer.daemon = True
        self._flush_timer.start()

    def _cancel_flush_timer(self) -> None:
        if self._flush_timer is not None:
            self._flush_timer.cancel()
            self._flush_timer = None

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
    "system/repair": "断尾修复审计",
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
