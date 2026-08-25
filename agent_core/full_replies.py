#!/usr/bin/env python3
"""
agent_core/full_replies.py — 「详细版」承诺兑现（截断稿持久化）
====================================================================
要点版截断时把完整原稿落盘；用户回复「详细版/完整版」时原样返回
（确定性兑现，不再靠模型重新生成——重生成会漂移，是假承诺）。

数据：memory-tree/data/full_replies.jsonl（保留最近 50 条）。
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "memory-tree" / "data"
STORE = DATA_DIR / "full_replies.jsonl"
_MAX = 50
_TTL = 1800  # 30 分钟内可兑现

_lock = threading.Lock()


def _load() -> list[dict]:
    if not STORE.is_file():
        return []
    out = []
    try:
        for line in open(STORE, encoding="utf-8").read().splitlines():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError:  # pragma: no cover
        pass
    return out[-_MAX:]


def save_full(truncated: str, full: str) -> None:
    """截断发生时保存完整原稿。"""
    f = (full or "").strip()
    t = (truncated or "").strip()
    if not f or not t or len(f) <= len(t) + 10:
        return
    rec = {
        "ts": time.time(),
        "key": hashlib.sha1(t[:200].encode("utf-8")).hexdigest()[:16],
        "truncated": t[:200],
        "full": f[:12000],
    }
    with _lock:
        try:
            STORE.parent.mkdir(parents=True, exist_ok=True)
            with open(STORE, "a", encoding="utf-8") as fp:
                fp.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except OSError:  # pragma: no cover
            pass


def get_full(message: str) -> str | None:
    """用户消息命中「详细版/完整版」请求时，返回最近一条完整原稿。"""
    m = (message or "").strip()
    if not re.search(r"(详细版|完整版|完整内容|完整回答|完整表格)", m):
        return None
    now = time.time()
    for rec in reversed(_load()):
        if now - rec.get("ts", 0) <= _TTL:
            return rec.get("full") or None
    return None
