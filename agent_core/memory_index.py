#!/usr/bin/env python3
"""
agent_core/memory_index.py — 跨会话向量检索记忆（零依赖本地实现）
====================================================================
对标 DSH/Hermes 的记忆能力补齐：不再只取"最近 N 条窗口"，而是按语义
相似度检索整个记忆库（字符 3-gram 哈希向量 + 余弦相似度）。

设计取舍（如实声明）：
  - 不依赖外部 embedding 服务/向量库（离线可用、无密钥、可审计）；
  - 字符 n-gram 对中文天然适配（无分词器依赖），代价是精度低于
    语义 embedding——对"回忆此前谈过的企业/断面/法条"类任务足够；
  - 4096 维稀疏向量，cosine 相似度，支持几千条记忆量级。

数据：memory-tree/data/memory.jsonl（每行 {role, content, ts, hash}）
索引：内存态（进程启动时从 jsonl 重建，写入即落盘）。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import time
from collections import Counter
from pathlib import Path

logger = logging.getLogger("eco.memory")

DATA_DIR = Path(__file__).resolve().parent.parent / "memory-tree" / "data"
MEMORY_FILE = DATA_DIR / "memory.jsonl"
DIM = 4096
NGRAM = 3
# 记忆库上限（可通过环境变量配置，默认 2000）
_MAX_RECORDS = int(os.environ.get("ECO_MEMORY_MAX_RECORDS", "2000"))
# 检索时先粗筛再精排，粗筛候选数（默认 100）
_SEARCH_PRESCREEN = int(os.environ.get("ECO_MEMORY_PRESCREEN", "100"))


def _ngram_vec(text: str) -> Counter[int]:
    """字符 n-gram 哈希向量：2-gram + 3-gram 混合（2-gram 权重减半，
    缓解词序敏感、提升短记录召回）。"""
    t = re.sub(r"\s+", "", text or "")
    vec: Counter[int] = Counter()
    if len(t) < 2:
        t = t + "  "  # 短文本补白保证有特征
    for n, w in ((3, 1.0), (2, 0.5)):
        if len(t) < n:
            continue
        for i in range(len(t) - n + 1):
            h = int(hashlib.md5(t[i:i + n].encode("utf-8")).hexdigest()[:6], 16)
            vec[h % DIM] += w
    return vec


def _cosine(a: Counter[int], b: Counter[int]) -> float:
    """共享特征覆盖度打分（n-gram 检索适配）：
    score = Σmin(a_i,b_i) / min(|a|,|b|)——短记录不被长查询范数稀释。"""
    if not a or not b:
        return 0.0
    shared = sum(min(a.get(k, 0), b.get(k, 0)) for k in a.keys() & b.keys())
    if shared <= 0:
        return 0.0
    return shared / min(sum(a.values()), sum(b.values()))


class MemoryIndex:
    """进程级单例：记忆记录 + 语义检索（预计算向量 + 关键词粗筛索引）"""

    def __init__(self, path: Path | None = None):
        self._path = path or MEMORY_FILE
        self._records: list[dict] = []
        self._lock = threading.Lock()
        # 预计算向量缓存: hash -> Counter
        self._vec_cache: dict[str, Counter] = {}
        # 关键词倒排索引: word -> set(record_indices)
        self._word_index: dict[str, set[int]] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.is_file():
            return
        try:
            with open(self._path, encoding="utf-8") as f:
                for line in f.readlines():
                    try:
                        rec = json.loads(line)
                        self._records.append(rec)
                    except json.JSONDecodeError:
                        continue
        except OSError:  # pragma: no cover
            pass
        # 截断到上限并重建索引
        self._records = self._records[-_MAX_RECORDS:]
        self._rebuild_index()

    def _rebuild_index(self):
        """重建向量缓存和关键词索引"""
        self._vec_cache.clear()
        self._word_index.clear()
        for idx, rec in enumerate(self._records):
            h = rec.get("hash", "")
            content = rec.get("content", "")
            if h and content:
                self._vec_cache[h] = _ngram_vec(content)
            # 提取关键词建倒排索引（中文字符串 + 英文单词）
            words = set(re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z]{3,}", content))
            for w in words:
                self._word_index.setdefault(w, set()).add(idx)

    def record(self, role: str, content: str, session_id: str = "default") -> None:
        """写入一条记忆（去噪：空/过短/纯符号跳过）"""
        c = (content or "").strip()
        if len(c) < 4 or not re.search(r"[\u4e00-\u9fffA-Za-z0-9]", c):
            return
        rec = {
            "role": role,
            "content": c[:600],
            "session_id": session_id,
            "ts": time.time(),
            "hash": hashlib.sha256(c[:200].encode("utf-8")).hexdigest()[:16],
        }
        with self._lock:
            # 去重：与最近一条同内容不重复写
            if self._records and self._records[-1].get("hash") == rec["hash"]:
                return
            self._records.append(rec)
            idx = len(self._records) - 1
            # 预计算向量并缓存
            self._vec_cache[rec["hash"]] = _ngram_vec(rec["content"])
            # 更新关键词索引
            words = set(re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z]{3,}", rec["content"]))
            for w in words:
                self._word_index.setdefault(w, set()).add(idx)
            # 容量控制
            if len(self._records) > _MAX_RECORDS:
                removed = len(self._records) - _MAX_RECORDS
                self._records = self._records[-_MAX_RECORDS:]
                # 重建索引（简单方案：截断后全量重建）
                self._rebuild_index()
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                with open(self._path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            except OSError as e:  # pragma: no cover — 落盘失败不影响业务
                logger.warning("[memory] 落盘失败: %s", e)

    def search(self, query: str, k: int = 5,
               exclude_recent: int = 0) -> list[dict]:
        """语义检索 top-k 条记忆（两层检索：关键词粗筛 + 余弦精排）"""
        q = (query or "").strip()
        if not q:
            return []
        qvec = _ngram_vec(q)
        # 提取查询关键词
        qwords = set(re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z]{3,}", q))

        scored: list[tuple[float, dict]] = []
        with self._lock:
            items = self._records[:-exclude_recent] if exclude_recent else self._records

            # 第一层：关键词粗筛（有索引时）
            if qwords and self._word_index:
                candidate_indices: set[int] = set()
                for w in qwords:
                    candidate_indices |= self._word_index.get(w, set())
                # 若无关键词命中，回退到全量扫描（兜底）
                if not candidate_indices:
                    candidate_indices = set(range(len(items)))
                # 限制粗筛候选数
                candidate_indices = sorted(candidate_indices)[:_SEARCH_PRESCREEN]
                candidates = [items[i] for i in candidate_indices if i < len(items)]
            else:
                candidates = items

            # 第二层：余弦相似度精排（使用预计算向量）
            for rec in candidates:
                h = rec.get("hash", "")
                rvec = self._vec_cache.get(h)
                if rvec is None:
                    rvec = _ngram_vec(rec.get("content", ""))
                    if h:
                        self._vec_cache[h] = rvec
                s = _cosine(qvec, rvec)
                if s > 0.08:
                    scored.append((s, rec))
        scored.sort(key=lambda x: -x[0])
        return [{"role": r.get("role", ""), "content": r.get("content", ""),
                 "score": round(s, 3)} for s, r in scored[:k]]

    def stats(self) -> dict:
        with self._lock:
            return {"records": len(self._records),
                    "file": str(self._path)}


_mem: MemoryIndex | None = None


def get_memory_index() -> MemoryIndex:
    global _mem
    if _mem is None:
        _mem = MemoryIndex()
    return _mem
