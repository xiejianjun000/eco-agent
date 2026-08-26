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
# 记忆库上限（超出淘汰最旧），可通过环境变量覆盖
_MAX_RECORDS = int(os.environ.get("ECO_MEMORY_MAX_RECORDS", "2000"))


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
    """进程级单例：记忆记录 + 语义检索。
    检索优化：
      1) 预计算并缓存每条记录的 n-gram 向量（避免每次查询重算 md5）；
      2) 倒排索引（特征哈希 -> 记录下标）只对与查询共享特征的候选做余弦打分。"""

    def __init__(self, path: Path | None = None):
        self._path = path or MEMORY_FILE
        self._records: list[dict] = []
        self._vecs: list[Counter[int]] = []  # 与 _records 平行的缓存向量
        self._inv: dict[int, set[int]] = {}  # 特征哈希 -> 记录下标集合
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
        self._rebuild_index()

    def _rebuild_index(self) -> None:
        """根据当前记录重建向量缓存 + 倒排索引"""
        vecs: list[Counter[int]] = []
        inv: dict[int, set[int]] = {}
        for i, rec in enumerate(self._records):
            v = _ngram_vec(rec.get("content", ""))
            vecs.append(v)
            for h in v:
                inv.setdefault(h, set()).add(i)
        self._vecs = vecs
        self._inv = inv

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
                # 淘汰最旧后下标整体左移，重建索引保证一致
                self._records = self._records[-_MAX_RECORDS:]
                self._rebuild_index()
            else:
                new_idx = len(self._records) - 1
                v = _ngram_vec(rec.get("content", ""))
                self._vecs.append(v)
                for h in v:
                    self._inv.setdefault(h, set()).add(new_idx)
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                with open(self._path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            except OSError as e:  # pragma: no cover — 落盘失败不影响业务
                logger.warning("[memory] 落盘失败: %s", e)

    def search(self, query: str, k: int = 5,
               exclude_recent: int = 0) -> list[dict]:
        """语义检索 top-k 条记忆（余弦相似度），返回 [{role, content, score}]。
        exclude_recent：跳过最近 N 条（避免把"当前正在进行的对话"当回忆）。
        优化：经倒排索引先取与查询共享特征的候选集，再做余弦打分，避免全量扫描。"""
        q = (query or "").strip()
        if not q:
            return []
        qvec = _ngram_vec(q)
        scored: list[tuple[float, dict]] = []
        with self._lock:
            items = self._records[:-exclude_recent] if exclude_recent else self._records
            if self._inv:
                cand: set[int] = set()
                for h in qvec:
                    cand |= self._inv.get(h, set())
                for i in cand:
                    if i >= len(items):
                        continue  # 落在 exclude_recent 区间的跳过
                    rec = self._records[i]
                    s = _cosine(qvec, self._vecs[i])  # 用缓存向量，避免重算
                    if s > 0.08:
                        scored.append((s, rec))
            else:  # pragma: no cover — 索引为空时回退全量扫描
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
