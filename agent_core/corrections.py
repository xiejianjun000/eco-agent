#!/usr/bin/env python3
"""
corrections.py — 用户纠错采集与注入

用户在 eco chat 中可用两种方式纠错：
  显式: "/correct 正确的说法是……"
  自然语言: "不对，应该是……" / "错了，正确的是……"（被识别）

纠错持久化到 ~/.eco/corrections.jsonl（内容/时间/上下文摘要/命中次数）。
后续任务构建提示词时，相关纠错作为高优先级动态注入（经 prompt_engine 校验层）。

CLI 管理: eco corrections list/remove/clear
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("corrections")

ECO_DIR = Path.home() / ".eco"
CORRECTIONS_FILE = ECO_DIR / "corrections.jsonl"

# 自然语言纠错识别 pattern
_NL_PATTERNS = [
    re.compile(r"^(?:不对|错了|不是这样|你搞错了|不正确)[，,。.\s]*(?:应该|应当)(?:是|为)?[：:，,。.\s]*(.+)$"),
    re.compile(r"^(?:不对|错了|不是这样|你搞错了|不正确)[，,。.\s]*(?:正确的是|是)[：:，,。.\s]*(.+)$"),
    re.compile(r"^(?:应该|应当)是[：:，,。\s]*(.+?)(?:[。.\s]*(?:才对|不是那样)?)$"),
]


def detect_correction(text: str) -> str | None:
    """识别用户输入是否为纠错，返回纠错内容；不是纠错返回 None"""
    t = text.strip()
    if t.startswith("/correct"):
        body = t[len("/correct"):].strip(" ：:")
        return body or None
    if t.startswith("/纠错"):
        body = t[len("/纠错"):].strip(" ：:")
        return body or None
    for pat in _NL_PATTERNS:
        m = pat.match(t)
        if m:
            body = m.group(1).strip()
            if len(body) >= 4:
                return body
    return None


class CorrectionStore:
    """纠错持久化存储"""

    def __init__(self, path: Path = None):
        self.path = Path(path) if path else CORRECTIONS_FILE
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> list[dict]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out

    def _save(self, items: list[dict]) -> None:
        with self.path.open("w", encoding="utf-8") as f:
            for it in items:
                f.write(json.dumps(it, ensure_ascii=False) + "\n")

    def add(self, content: str, context_summary: str = "") -> dict:
        """新增纠错；与已有纠错高度相似时增加命中次数"""
        items = self._load()
        for it in items:
            if it["content"] == content or content in it["content"] or it["content"] in content:
                it["hits"] = it.get("hits", 1) + 1
                it["last_seen"] = datetime.now().isoformat(timespec="seconds")
                self._save(items)
                logger.info(f"[Corrections] 命中已有纠错（hits={it['hits']}）: {content[:50]}")
                return it
        entry = {
            "id": len(items) + 1,
            "content": content,
            "context_summary": context_summary[:200],
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "hits": 1,
        }
        items.append(entry)
        self._save(items)
        logger.info(f"[Corrections] 新增纠错#{entry['id']}: {content[:50]}")
        return entry

    def list_all(self) -> list[dict]:
        return self._load()

    def remove(self, idx: int) -> bool:
        items = self._load()
        for i, it in enumerate(items):
            if it.get("id") == idx:
                items.pop(i)
                self._save(items)
                return True
        return False

    def clear(self) -> int:
        n = len(self._load())
        self._save([])
        return n

    def relevant(self, question: str, limit: int = 3) -> list[dict]:
        """按关键词重叠挑选与当前问题相关的纠错（简单词重合打分）"""
        items = self._load()
        if not items:
            return []
        q_chars = set(question)
        scored = []
        for it in items:
            text = it["content"] + it.get("context_summary", "")
            overlap = sum(1 for ch in set(text) if ch in q_chars)
            scored.append((overlap + it.get("hits", 1), it))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [it for _, it in scored[:limit]]

    def inject_into_prompt_engine(self, engine, question: str = "", task_id: str = "") -> int:
        """将相关纠错作为高优先级动态注入（经引擎校验层），返回注入条数"""
        cands = self.relevant(question) if question else self.list_all()[:3]
        n = 0
        for it in cands:
            content = f"【用户纠错·高优先级】{it['content']}（请在本回答中严格遵守此纠正）"
            if engine.inject(content, source="correction", task_id=task_id):
                n += 1
        return n
