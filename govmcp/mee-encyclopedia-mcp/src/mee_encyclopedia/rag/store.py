"""轻量 RAG 知识库：倒排索引 + 简单打分，支持本地文档批量入库与检索。"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

STOPWORDS = {"的", "了", "和", "与", "在", "是", "为", "对", "及", "或", "等", "第", "条", "项", "款"}


def _tokenize(text: str) -> list[str]:
    """中文按 2-gram + 英文按词切分，返回 token 列表。"""
    tokens: list[str] = []
    text = text.lower()
    # 英文/数字
    for m in re.finditer(r"[a-z0-9]+", text):
        tokens.append(m.group())
    # 中文
    zh = re.sub(r"[^\u4e00-\u9fff]", "", text)
    for i in range(len(zh) - 1):
        bigram = zh[i : i + 2]
        if bigram[0] not in STOPWORDS and bigram[1] not in STOPWORDS:
            tokens.append(bigram)
    return tokens


class RagStore:
    """简单可持久化 RAG 存储。"""

    def __init__(self, base_dir: Path) -> None:
        self._base = base_dir
        self._base.mkdir(parents=True, exist_ok=True)
        self._docs: dict[str, dict[str, Any]] = {}
        self._index: dict[str, list[str]] = {}
        self._load()

    def _index_path(self) -> Path:
        return self._base / "rag_index.json"

    def _load(self) -> None:
        try:
            p = self._index_path()
            if p.exists():
                data = json.loads(p.read_text(encoding="utf-8"))
                self._docs = data.get("docs", {})
                self._index = data.get("index", {})
        except Exception as exc:  # noqa: BLE001
            logger.debug("RAG 索引加载失败: %s", exc)

    def add(self, doc_id: str, title: str, text: str, source: str = "") -> None:
        self._docs[doc_id] = {
            "id": doc_id,
            "title": title,
            "text": text,
            "source": source,
            "ts": time.time(),
        }
        for tok in _tokenize(title + " " + text):
            self._index.setdefault(tok, [])
            if doc_id not in self._index[tok]:
                self._index[tok].append(doc_id)
        self._save()

    def add_many(self, docs: list[dict[str, str]]) -> int:
        for d in docs:
            self.add(d["id"], d.get("title", ""), d.get("text", ""), d.get("source", ""))
        return len(docs)

    def _save(self) -> None:
        try:
            self._index_path().write_text(
                json.dumps({"docs": self._docs, "index": self._index}, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("RAG 索引保存失败: %s", exc)

    def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """检索并返回 Top-K 片段（含相关分数）。"""
        q_tokens = _tokenize(query)
        if not q_tokens:
            return []
        scores: dict[str, float] = {}
        for tok in q_tokens:
            for doc_id in self._index.get(tok, []):
                scores[doc_id] = scores.get(doc_id, 0.0) + 1.0
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[: top_k * 3]
        results = []
        for doc_id, score in ranked:
            doc = self._docs.get(doc_id)
            if not doc:
                continue
            snippet = _snippet(doc["text"], query, 500)
            results.append(
                {
                    "id": doc_id,
                    "title": doc["title"],
                    "source": doc["source"],
                    "score": round(score, 2),
                    "snippet": snippet,
                }
            )
            if len(results) >= top_k:
                break
        return results

    def stats(self) -> dict:
        return {"docs": len(self._docs), "tokens": len(self._index), "base": str(self._base)}


def _snippet(text: str, query: str, length: int = 500) -> str:
    """截取包含查询词的片段。"""
    idx = text.find(query)
    if idx == -1:
        for tok in _tokenize(query)[:1]:
            idx = text.find(tok)
            if idx != -1:
                break
    if idx == -1:
        return text[:length]
    start = max(0, idx - length // 2)
    return text[start : start + length]
