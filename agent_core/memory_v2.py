#!/usr/bin/env python3
"""memory_v2.py — 五星记忆系统（HNSW + 时间图 + Redis 缓存）"""
import json, hashlib, logging, os, threading, time
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger("eco.memory_v2")

try:
    import hnswlib
    HNSW_AVAILABLE = True
except ImportError:
    HNSW_AVAILABLE = False

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

DIM = 768
MAX_ELEMENTS = 10000
EF_CONSTRUCTION = 200
M = 16

class TemporalFact:
    def __init__(self, fact: str, valid_from=None, valid_until=None, source=""):
        self.fact = fact
        self.valid_from = valid_from or datetime.now()
        self.valid_until = valid_until
        self.source = source
        self.invalidated_by = None
    def is_valid(self, at=None):
        at = at or datetime.now()
        if self.valid_until and at > self.valid_until:
            return False
        return at >= self.valid_from
    def invalidate(self, reason: str):
        self.valid_until = datetime.now()
        self.invalidated_by = reason
    def to_dict(self):
        return {"fact": self.fact, "valid_from": self.valid_from.isoformat(),
                "valid_until": self.valid_until.isoformat() if self.valid_until else None,
                "source": self.source, "invalidated_by": self.invalidated_by}

class HNSWMemoryIndex:
    def __init__(self, dim=DIM, max_elements=MAX_ELEMENTS):
        self.dim = dim
        self.max_elements = max_elements
        self._index = None
        self._items = []
        self._lock = threading.Lock()
        if HNSW_AVAILABLE:
            self._init_index()
    def _init_index(self):
        self._index = hnswlib.Index(space='cosine', dim=self.dim)
        self._index.init_index(max_elements=self.max_elements, ef_construction=EF_CONSTRUCTION, M=M)
        self._index.set_ef(50)
    def _get_embedding(self, text: str) -> list[float]:
        import re
        t = re.sub(r"\s+", "", text or "")
        vec = [0.0] * self.dim
        for n in (3, 2):
            if len(t) < n: continue
            for i in range(len(t) - n + 1):
                h = int(hashlib.md5(t[i:i + n].encode("utf-8")).hexdigest()[:8], 16)
                vec[h % self.dim] += 1.0
        norm = sum(x ** 2 for x in vec) ** 0.5
        if norm > 0:
            vec = [x / norm for x in vec]
        return vec
    def add(self, text: str, metadata=None) -> int:
        if not HNSW_AVAILABLE: return -1
        vec = self._get_embedding(text)
        with self._lock:
            idx = len(self._items)
            self._items.append({"text": text, "metadata": metadata or {}, "idx": idx})
            self._index.add_items([vec], [idx])
            return idx
    def search(self, query: str, k=5) -> list[dict]:
        if not HNSW_AVAILABLE or not self._items: return []
        vec = self._get_embedding(query)
        with self._lock:
            labels, distances = self._index.knn_query([vec], k=k)
            results = []
            for idx, dist in zip(labels[0], distances[0]):
                item = self._items[idx]
                results.append({"text": item["text"], "metadata": item["metadata"], "score": float(1 - dist)})
            return results

class TemporalGraphMemory:
    def __init__(self):
        self._facts = {}
        self._lock = threading.Lock()
    def add_fact(self, entity: str, fact: str, source=""):
        with self._lock:
            if entity not in self._facts: self._facts[entity] = []
            for old in self._facts[entity]:
                if old.is_valid() and old.fact != fact:
                    old.invalidate(f"被替代: {fact[:50]}")
            self._facts[entity].append(TemporalFact(fact, source=source))
    def query(self, entity: str, at=None) -> list:
        at = at or datetime.now()
        with self._lock:
            return [f for f in self._facts.get(entity, []) if f.is_valid(at)]
    def get_history(self, entity: str) -> list:
        with self._lock:
            return [f.to_dict() for f in self._facts.get(entity, [])]

class RedisCache:
    def __init__(self, host="localhost", port=6379, db=0):
        self._client = None
<<<<<<< HEAD
        # 健壮性修复：Redis 不可达时 redis-py 的连接重试可能挂死进程，
        # 先做 1s 裸 socket 探针，不通直接降级（不创建客户端）
        if REDIS_AVAILABLE and self._probe(host, port):
            try:
                self._client = redis.Redis(host=host, port=port, db=db, decode_responses=True,
                                           socket_connect_timeout=2, socket_timeout=2)
                self._client.ping()
            except Exception as e:
                self._client = None
                logger.warning(f"[Redis] 连接失败: {e}")

    @staticmethod
    def _probe(host: str, port: int, timeout: float = 1.0) -> bool:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        try:
            s.connect((host, port))
            return True
        except OSError:
            return False
        finally:
            s.close()
=======
        if REDIS_AVAILABLE:
            try:
                self._client = redis.Redis(host=host, port=port, db=db, decode_responses=True)
                self._client.ping()
            except Exception as e:
                logger.warning(f"[Redis] 连接失败: {e}")
>>>>>>> a3797b5 (Add 10 Anthropic Skills + zhihu-fetch-skill)
    def get(self, key: str) -> str | None:
        return self._client.get(key) if self._client else None
    def set(self, key: str, value: str, ttl=3600):
        if self._client: self._client.setex(key, ttl, value)

class MemoryV2:
    def __init__(self, index_path=None):
        self.hnsw = HNSWMemoryIndex()
        self.graph = TemporalGraphMemory()
        self.cache = RedisCache()
        self._index_path = index_path or Path("memory-tree/data/memory_v2.index")
    def record(self, role: str, content: str, session_id="default"):
        self.hnsw.add(content, {"role": role, "session_id": session_id, "ts": time.time()})
        self._extract_facts(content)
        self.cache.set(f"eco:memory:latest:{session_id}", content, ttl=3600)
    def _extract_facts(self, text: str):
        import re
        for m in re.finditer(r"([\u4e00-\u9fff\w]{2,20})(?:是|为|等于)([\u4e00-\u9fff\w]{2,50})", text):
<<<<<<< HEAD
            full_entity = m.group(1)
            self.graph.add_fact(full_entity, m.group(2), source="conversation")
            # 实体粒度修复：附加主体名词（“的”之前）作为实体，
            # 使“企业42的许可证编号是XK...”可用“企业42”查询
            head = full_entity.split("的")[0]
            if head != full_entity and len(head) >= 2:
                self.graph.add_fact(head, m.group(2), source="conversation")
=======
            self.graph.add_fact(m.group(1), m.group(2), source="conversation")
>>>>>>> a3797b5 (Add 10 Anthropic Skills + zhihu-fetch-skill)
    def search(self, query: str, k=5) -> list[dict]:
        key = f"eco:memory:search:{hashlib.md5(query.encode()).hexdigest()[:8]}"
        cached = self.cache.get(key)
        if cached: return json.loads(cached)
        results = self.hnsw.search(query, k=k)
        import re
        for entity in re.findall(r"[\u4e00-\u9fff\w]{2,10}", query):
            for f in self.graph.query(entity):
                results.append({"text": f.fact, "metadata": {"entity": entity, "source": "temporal_graph"}, "score": 0.95})
        self.cache.set(key, json.dumps(results[:k], ensure_ascii=False), ttl=300)
        return results[:k]
