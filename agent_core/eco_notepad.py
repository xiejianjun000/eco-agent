#!/usr/bin/env python3
"""
agent_core/eco_notepad.py — 结构化便签簿（M4 P1-2 / Hermes cron notepad 对标）
==============================================================================
对标基准：Hermes ``cron/notepad.py``（per-job durable KV scratchpad）。
Hermes 以 cron job_id 为键、为每次定时 wake-up 跨会话携带游标/水位/watchlist，
写路径只走 CLI（agent 用终端工具调），不走模型工具；每次运行注入 prompt 前读取。

eco-agent 无 cron job 抽象，等价物是"任务/会话粒度的结构化 note"，因此本模块
把 notepad 落为 **~/.eco/notepad.jsonl** 单文件结构化便签（JSONL 只追加，
归档为原地标记 archived，不做物理删除），供：
  - L4/用户通过 CLI 记录持续上下文（note）；
  - monitor 巡检通道写入免 LLM 的变更告警（kind=alert，见 eco_monitor.py）；
  - agent 短时 scratch（kind=scratch，等价 Hermes job 内 scratchpad）。

大小契约沿用 Hermes：
  - MAX_VALUE_BYTES  = 16 KB/条（content，UTF-8 字节计）——对齐 Hermes MAX_VALUE_BYTES
  - MAX_TITLE_CHARS  = 256 字符（title，对齐 Hermes MAX_KEY_CHARS=128 的宽松版）
  - MAX_FILE_BYTES   = 8 MB/文件（超限拒绝写入并提示归档）
单测/多实例隔离沿用 eco_state 约定：HOME_ECO_DIR 可由环境变量 ECO_HOME 覆盖。

行 schema（每行一个 JSON 对象）：
  {
    "id": "hex12", "kind": "note|scratch|alert",
    "title": str, "content": str, "tags": [str],
    "ref": Optional[str],            # 关联对象：task/peer/scheduled_job id
    "created_at": ISO, "updated_at": ISO,
    "archived": false
  }
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("eco.notepad")

# 与 eco_state.py 共用家目录状态根（ECO_HOME 可覆盖，测试/多实例隔离）
HOME_ECO_DIR = Path(os.environ.get("ECO_HOME", str(Path.home() / ".eco")))

NOTEPAD_FILE_NAME = "notepad.jsonl"

# ── 大小契约（对标 Hermes cron/notepad.py）─────────────────────────
MAX_VALUE_BYTES = 16 * 1024  # Hermes MAX_VALUE_BYTES：单条 content 16KB
MAX_TITLE_CHARS = 256  # Hermes MAX_KEY_CHARS=128 的宽松等价
MAX_FILE_BYTES = 8 * 1024 * 1024  # 文件级保护上限（8MB，超出提示归档）

VALID_KINDS = ("note", "scratch", "alert")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class NotepadStore:
    """~/.eco/notepad.jsonl 的结构化便签存取。"""

    def __init__(self, home_root: Optional[Path] = None):
        root = Path(home_root) if home_root is not None else HOME_ECO_DIR
        self.root = root
        self.path = root / NOTEPAD_FILE_NAME
        self.path.parent.mkdir(parents=True, exist_ok=True)

    # ── 底层 IO ──
    def _read_rows(self) -> List[Dict[str, Any]]:
        """读全部行；坏行跳过并在返回中携带 corrupt 行数语义（stats 用）。"""
        rows: List[Dict[str, Any]] = []
        if not self.path.exists():
            return rows
        raw = self.path.read_text(encoding="utf-8")
        for line in raw.splitlines():
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict) and obj.get("id"):
                    rows.append(obj)
                else:
                    logger.warning("notepad: 跳过非 note 行 %s", obj)
            except (ValueError, UnicodeDecodeError):
                logger.warning("notepad: 跳过坏行 %s", line[:80])
        return rows

    def _append(self, obj: Dict[str, Any]) -> None:
        if self.path.exists() and self.path.stat().st_size > MAX_FILE_BYTES:
            raise ValueError(
                f"notepad.jsonl 超过 {MAX_FILE_BYTES // (1024 * 1024)}MB 上限：请先 `eco notepad archive` 归档历史条目"
            )
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(obj, ensure_ascii=False) + "\n")

    # ── 写路径 ──
    def add(
        self, title: str, content: str = "", tags: Optional[List[str]] = None, kind: str = "note", ref: Optional[str] = None
    ) -> Dict[str, Any]:
        """新增一条结构化便签（只追加）。"""
        if kind not in VALID_KINDS:
            raise ValueError(f"kind 必须是 {VALID_KINDS} 之一，got {kind!r}")
        title = (title or "").strip()
        if not title:
            raise ValueError("title 不能为空（等价 Hermes notepad 的 key）")
        if len(title) > MAX_TITLE_CHARS:
            raise ValueError(f"title 超长（上限 {MAX_TITLE_CHARS} 字符）")
        content = content or ""
        if len(content.encode("utf-8")) > MAX_VALUE_BYTES:
            raise ValueError(f"content 超长（上限 {MAX_VALUE_BYTES // 1024}KB，UTF-8 字节计）")
        tags = [str(t).strip() for t in (tags or []) if str(t).strip()]
        now = _now()
        note = {
            "id": uuid.uuid4().hex[:12],
            "kind": kind,
            "title": title,
            "content": content,
            "tags": tags,
            "ref": ref or None,
            "created_at": now,
            "updated_at": now,
            "archived": False,
        }
        self._append(note)
        logger.info("notepad: add %s %s", note["id"], title[:40])
        return note

    # ── 读路径 ──
    def list(
        self,
        tag: Optional[str] = None,
        include_archived: bool = False,
        kinds: Optional[List[str]] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        notes = self._read_rows()
        if not include_archived:
            notes = [n for n in notes if not n.get("archived")]
        if kinds:
            notes = [n for n in notes if n.get("kind") in kinds]
        if tag:
            notes = [n for n in notes if tag in n.get("tags", [])]
        notes.sort(key=lambda n: n.get("created_at", ""), reverse=True)
        if limit is not None:
            notes = notes[: max(0, int(limit))]
        return notes

    def get(self, note_id: str) -> Optional[Dict[str, Any]]:
        for n in self._read_rows():
            if n["id"] == note_id:
                return n
        return None

    def search(self, query: str, tag: Optional[str] = None, include_archived: bool = False) -> List[Dict[str, Any]]:
        q = (query or "").lower()
        if not q:
            return []
        hits = []
        for n in self._read_rows():
            if not include_archived and n.get("archived"):
                continue
            if tag and tag not in n.get("tags", []):
                continue
            hay = " ".join([n.get("title", ""), n.get("content", ""), " ".join(n.get("tags", [])), n.get("ref") or ""]).lower()
            if q in hay:
                hits.append(n)
        hits.sort(key=lambda n: n.get("created_at", ""), reverse=True)
        return hits

    # ── 归档（只做原地标记，不做物理删除）─────────────────────────
    def archive(self, note_id: str) -> bool:
        rows = self._read_rows()
        changed = False
        for n in rows:
            if n["id"] == note_id and not n.get("archived"):
                n["archived"] = True
                n["updated_at"] = _now()
                changed = True
        if not changed:
            return False
        # 原子回写：temp + rename
        tmp = self.path.with_suffix(".jsonl.tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            for n in rows:
                fh.write(json.dumps(n, ensure_ascii=False) + "\n")
        tmp.replace(self.path)
        return True

    def stats(self) -> Dict[str, Any]:
        rows = self._read_rows()
        by_kind: Dict[str, int] = {}
        for n in rows:
            by_kind[n.get("kind", "?")] = by_kind.get(n.get("kind", "?"), 0) + 1
        return {
            "file": str(self.path),
            "exists": self.path.exists(),
            "size_bytes": self.path.stat().st_size if self.path.exists() else 0,
            "total": len(rows),
            "archived": sum(1 for n in rows if n.get("archived")),
            "by_kind": by_kind,
        }

    def sha256(self) -> str:
        if not self.path.exists():
            return ""
        h = hashlib.sha256()
        h.update(self.path.read_bytes())
        return h.hexdigest()
