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
_MAX_RECORDS = 2000  # 记忆库上限（超出淘汰最旧）


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
    """进程级单例：记忆记录 + 语义检索。"""

    def __init__(self, path: Path | None = None):
        self._path = path or MEMORY_FILE
        self._records: list[dict] = []
        self._lock = threading.Lock()
        self._load()

    def _load(self) -> None:
        if not self._path.is_file():
            return
        try:
            with open(self._path, encoding="utf-8") as f:
                for line in f.readlines():
                    try:
                        self._records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except OSError:  # pragma: no cover
            pass
        self._records = self._records[-_MAX_RECORDS:]

    def record(self, role: str, content: str, session_id: str = "default") -> None:
        """写入一条记忆（去噪：空/过短/纯符号跳过）。"""
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
            if len(self._records) > _MAX_RECORDS:
                self._records = self._records[-_MAX_RECORDS:]
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                with open(self._path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            except OSError as e:  # pragma: no cover — 落盘失败不影响业务
                logger.warning("[memory] 落盘失败: %s", e)

    def search(self, query: str, k: int = 5,
               exclude_recent: int = 0) -> list[dict]:
        """语义检索 top-k 条记忆。优先混合检索（BM25 中文 bigram + 向量 RRF 融合，
        hybrid_retrieval.py 已实现但此前未通电接入）；失败/无结果优雅降级字符 n-gram。
        exclude_recent：跳过最近 N 条（避免把"当前正在进行的对话"当回忆）。"""
        q = (query or "").strip()
        if not q:
            return []
        with self._lock:
            items = self._records[:-exclude_recent] if exclude_recent else self._records
        # 通电：混合检索（BM25 bigram + 向量，RRF 融合）——比纯字符 n-gram 对中文更准
        try:
            from agent_core.hybrid_retrieval import hybrid_search
            events = [{"id": r.get("hash", ""), "content": r.get("content", ""),
                       "kind": r.get("role", "")} for r in items]
            hits = hybrid_search(events, q, top_k=k, namespace="memory", embed=True)
            if hits:
                by_id = {r.get("hash", ""): r for r in items}
                out = []
                for h in hits:
                    # hybrid 返回的 id 带 namespace 前缀（memory:hash），剥掉前缀再回查原记录
                    rid = str(h.get("id", "")).rsplit(":", 1)[-1]
                    r = by_id.get(rid)
                    if r:
                        out.append({"role": r.get("role", ""), "content": r.get("content", ""),
                                    "score": round(h.get("score", 0.0), 3),
                                    "channel": h.get("channel", "")})
                if out:
                    return out
        except Exception:  # noqa: BLE001 — hybrid 失败/缺依赖降级 n-gram
            pass
        # 降级：字符 n-gram 余弦（原实现，离线零依赖兜底）
        qvec = _ngram_vec(q)
        scored: list[tuple[float, dict]] = []
        for rec in items:
            s = _cosine(qvec, _ngram_vec(rec.get("content", "")))
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
