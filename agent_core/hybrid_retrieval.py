#!/usr/bin/env python3
"""
hybrid_retrieval.py — 混合检索（Phase B2）

将工作区历史 / Memory Tree 检索从"FTS5 关键词 + 全量截断"升级为：
  BM25（纯 Python Okapi，中文走 bigram 分词）+ 向量余弦 → RRF(k=60) 融合排序；
  无 embedding 配置/调用失败时优雅降级为 BM25-only。

向量通道：
  - OpenAI 兼容 /embeddings 端点（provider 的 PROVIDERS 配置含 embedding_model 才启用；
    如 Moonshot moonshot-v1-embedding 系列，DeepSeek 无 embedding → 自动禁用）
  - 也可用 ECO_EMBED_PROVIDER=kimi 显式指定用哪个 provider 的 embedding
  - 向量本地存 sqlite（hybrid_vec 表，numpy 计算余弦），按 doc_id 幂等更新

检索结果带来源标注：每条命中含 {"id", "text", "source", "score", "channel"}，
channel ∈ {"hybrid", "bm25"}，标明是否融合了向量通道。
"""

import json
import logging
import math
import os
import re
import sqlite3
import time
from collections import Counter
from pathlib import Path

logger = logging.getLogger("hybrid_retrieval")

ECO_DIR = Path.home() / ".eco"
DEFAULT_VEC_DB = ECO_DIR / "hybrid_vectors.db"
RRF_K = 60  # RRF 融合常数

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+|[一-鿿]")


def tokenize(text: str) -> list[str]:
    """混合分词：英文/数字整词 + 中文单字 bigram（中文单字本身也保留，提升召回）"""
    text = (text or "").lower()
    tokens: list[str] = []
    for m in _TOKEN_RE.finditer(text):
        t = m.group(0)
        if re.fullmatch(r"[一-鿿]", t):
            tokens.append(t)
        else:
            tokens.append(t)
    # 中文 bigram
    cjk = "".join(ch if re.fullmatch(r"[一-鿿]", ch) else " " for ch in text)
    for seg in cjk.split():
        tokens.extend(seg[i : i + 2] for i in range(len(seg) - 1))
    return tokens


class BM25Index:
    """纯 Python Okapi BM25（内存索引，适合工作区级小规模语料）"""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.doc_ids: list[str] = []
        self.doc_len: list[int] = []
        self.tf: list[Counter] = []
        self.df: Counter = Counter()
        self.avgdl = 0.0

    def build(self, docs: list[tuple[str, str]]):
        """docs: [(doc_id, text)]"""
        self.doc_ids, self.doc_len, self.tf = [], [], []
        self.df = Counter()
        for doc_id, text in docs:
            toks = tokenize(text)
            self.doc_ids.append(doc_id)
            self.doc_len.append(len(toks))
            tf = Counter(toks)
            self.tf.append(tf)
            for t in tf:
                self.df[t] += 1
        n = len(self.doc_ids)
        self.avgdl = sum(self.doc_len) / n if n else 0.0

    def score(self, query: str) -> list[tuple[str, float]]:
        """返回 [(doc_id, bm25_score)] 降序，仅含得分 > 0 的文档"""
        n = len(self.doc_ids)
        if not n:
            return []
        q_toks = tokenize(query)
        out: list[tuple[str, float]] = []
        for i, tf in enumerate(self.tf):
            score = 0.0
            dl = self.doc_len[i] or 1
            for t in q_toks:
                f = tf.get(t, 0)
                if not f:
                    continue
                df = self.df[t]
                idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
                score += idf * (f * (self.k1 + 1)) / (f + self.k1 * (1 - self.b + self.b * dl / (self.avgdl or 1)))
            if score > 0:
                out.append((self.doc_ids[i], score))
        out.sort(key=lambda x: x[1], reverse=True)
        return out


def rrf_fuse(rankings: list[list[str]], k: int = RRF_K) -> list[tuple[str, float]]:
    """Reciprocal Rank Fusion：rankings 为多个按名次排序的 doc_id 列表，
    返回 [(doc_id, rrf_score)] 降序"""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    out = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return out


class EmbeddingClient:
    """OpenAI 兼容 embedding 客户端。
    可用性判定：ECO_LLM_DISABLE 未开 + provider（或 ECO_EMBED_PROVIDER 指定者）
    配置了 embedding_model 且存在对应 API key。DeepSeek 无 embedding → 自动禁用。"""

    def __init__(self):
        from agent_core.llm_client import PROVIDERS

        self._disabled = os.environ.get("ECO_LLM_DISABLE", "").strip().lower() in ("1", "true", "yes")
        env = {}
        env_file = Path.home() / ".eco" / ".env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
        self._env = env
        name = (
            os.environ.get("ECO_EMBED_PROVIDER")
            or env.get("ECO_EMBED_PROVIDER")
            or os.environ.get("ECO_PROVIDER")
            or env.get("ECO_PROVIDER", "deepseek")
        )
        prov = PROVIDERS.get(name, {})
        self.model = prov.get("embedding_model") or os.environ.get("ECO_EMBED_MODEL", "")
        key_env = prov.get("api_key_env", "")
        self._api_key = os.environ.get(key_env) or env.get(key_env, "") if key_env else ""
        self._base_url = prov.get("base_url", "")
        self._httpx = None
        try:
            import httpx

            self._httpx = httpx
        except ImportError:
            pass

    def available(self) -> bool:
        return (
            not self._disabled and self._httpx is not None and bool(self.model) and bool(self._api_key) and bool(self._base_url)
        )

    def embed(self, texts: list[str], timeout: float = 30.0) -> list[list[float]] | None:
        """批量取向量；失败返回 None（调用方降级 BM25-only）"""
        if not self.available() or not texts:
            return None
        try:
            resp = self._httpx.post(
                f"{self._base_url}/embeddings",
                headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                json={"model": self.model, "input": texts},
                timeout=timeout,
            )
            if resp.status_code != 200:
                logger.warning(f"[embed] HTTP {resp.status_code}: {resp.text[:200]}")
                return None
            data = resp.json().get("data", [])
            data.sort(key=lambda d: d.get("index", 0))
            return [d.get("embedding", []) for d in data]
        except Exception as e:
            logger.warning(f"[embed] {type(e).__name__}: {e}")
            return None


class VectorStore:
    """sqlite 本地向量库：hybrid_vec(doc_id PK, source, text, vec JSON)，numpy 余弦"""

    def __init__(self, db_path: Path | None = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_VEC_DB
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS hybrid_vec ("
                "  doc_id TEXT PRIMARY KEY,"
                "  source TEXT DEFAULT '',"
                "  text TEXT DEFAULT '',"
                "  vec TEXT DEFAULT '',"
                "  updated_at REAL"
                ")"
            )

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db_path))

    def upsert(self, doc_id: str, vec: list[float], source: str = "", text: str = ""):
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO hybrid_vec (doc_id, source, text, vec, updated_at) "
                "VALUES (?,?,?,?,?) ON CONFLICT(doc_id) DO UPDATE SET "
                "source=excluded.source, text=excluded.text, vec=excluded.vec, "
                "updated_at=excluded.updated_at",
                (doc_id, source, text[:500], json.dumps(vec), time.time()),
            )

    def existing_ids(self, doc_ids: list[str]) -> set[str]:
        if not doc_ids:
            return set()
        with self._conn() as conn:
            q = f"SELECT doc_id FROM hybrid_vec WHERE doc_id IN ({','.join('?' * len(doc_ids))})"
            return {r[0] for r in conn.execute(q, doc_ids).fetchall()}

    def cosine_rank(self, qvec: list[float], doc_ids: list[str] | None = None, top_k: int = 10) -> list[str]:
        """numpy 余弦相似度排序，返回 doc_id 降序列表"""
        try:
            import numpy as np
        except ImportError:
            logger.warning("[vector] numpy 不可用，跳过向量通道")
            return []
        with self._conn() as conn:
            if doc_ids:
                q = f"SELECT doc_id, vec FROM hybrid_vec WHERE doc_id IN ({','.join('?' * len(doc_ids))})"
                rows = conn.execute(q, doc_ids).fetchall()
            else:
                rows = conn.execute("SELECT doc_id, vec FROM hybrid_vec").fetchall()
        if not rows:
            return []
        q = np.asarray(qvec, dtype=float)
        qn = np.linalg.norm(q)
        if qn == 0:
            return []
        scored = []
        for doc_id, vec_json in rows:
            try:
                v = np.asarray(json.loads(vec_json), dtype=float)
                vn = np.linalg.norm(v)
                if vn == 0 or v.shape != q.shape:
                    continue
                scored.append((doc_id, float(np.dot(q, v) / (qn * vn))))
            except (ValueError, json.JSONDecodeError):
                continue
        scored.sort(key=lambda x: x[1], reverse=True)
        return [d for d, s in scored[:top_k] if s > 0]


class HybridRetriever:
    """
    BM25 + 向量 混合检索器（RRF k=60 融合，无向量时降级 BM25-only）。

    用法：
        r = HybridRetriever(namespace="workspace:合力砖厂")
        r.index([{"id": "h1", "text": "...", "source": "history"}])
        hits = r.search("按日连续处罚", top_k=3)
    每次 index() 重建 BM25（工作区级语料规模小，重建代价可忽略），
    向量增量 upsert 进 sqlite（namespace 作为 doc_id 前缀隔离）。
    """

    def __init__(self, namespace: str = "default", vec_db: Path | None = None, embed_client: EmbeddingClient | None = None):
        self.namespace = namespace
        self.embed_client = embed_client if embed_client is not None else EmbeddingClient()
        self.store = VectorStore(vec_db)
        self.docs: dict[str, dict] = {}  # full doc_id -> {"id","text","source"}
        self._bm25 = BM25Index()
        self.last_channel = "bm25"  # 最近一次检索实际使用的通道

    def _fid(self, doc_id: str) -> str:
        return f"{self.namespace}:{doc_id}"

    @property
    def vector_enabled(self) -> bool:
        return self.embed_client.available()

    def index(self, docs: list[dict], embed: bool = True):
        """docs: [{"id","text","source"}]。BM25 全量重建，向量增量补齐。"""
        self.docs = {self._fid(d["id"]): {**d, "id": self._fid(d["id"])} for d in docs if d.get("text")}
        self._bm25.build([(fid, d["text"]) for fid, d in self.docs.items()])
        if not embed or not self.vector_enabled or not self.docs:
            return
        fids = list(self.docs)
        missing = [f for f in fids if f not in self.store.existing_ids(fids)]
        if not missing:
            return
        vecs = self.embed_client.embed([self.docs[f]["text"][:2000] for f in missing])
        if vecs is None:
            return
        for fid, vec in zip(missing, vecs, strict=False):
            if vec:
                d = self.docs[fid]
                self.store.upsert(fid, vec, source=d.get("source", ""), text=d["text"])

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """RRF(k=60) 融合 BM25 名次与向量名次；向量不可用 → BM25-only。
        返回 [{"id","text","source","score","channel"}]，score 为 RRF 分。"""
        if not self.docs:
            self.last_channel = "bm25"
            return []
        bm25_rank = [d for d, _ in self._bm25.score(query)]
        vec_rank: list[str] = []
        used_vector = False
        if self.vector_enabled:
            qvec = self.embed_client.embed([query[:2000]])
            if qvec and qvec[0]:
                vec_rank = self.store.cosine_rank(qvec[0], doc_ids=list(self.docs), top_k=top_k * 3)
                used_vector = bool(vec_rank)
        rankings = [bm25_rank] + ([vec_rank] if used_vector else [])
        fused = rrf_fuse(rankings, k=RRF_K)
        self.last_channel = "hybrid" if used_vector else "bm25"
        out = []
        for fid, score in fused[:top_k]:
            d = self.docs.get(fid)
            if d:
                out.append(
                    {
                        "id": fid,
                        "text": d["text"],
                        "source": d.get("source", ""),
                        "score": round(score, 6),
                        "channel": self.last_channel,
                    }
                )
        return out


# ── 便捷函数：对任意事件列表做一次性混合检索（工作区历史/Memory Tree 共用）──


def hybrid_search(
    events: list[dict], query: str, top_k: int = 5, namespace: str = "adhoc", embed: bool = True, vec_db: Path | None = None
) -> list[dict]:
    """events: [{"content"/"text", "kind"/"source", ...}] → top_k 命中（带来源标注）"""
    docs = []
    for i, e in enumerate(events):
        text = e.get("content") or e.get("text") or ""
        if not text.strip():
            continue
        docs.append({"id": str(e.get("id") or f"e{i}"), "text": text, "source": e.get("kind") or e.get("source") or namespace})
    r = HybridRetriever(namespace=namespace, vec_db=vec_db)
    r.index(docs, embed=embed)
    return r.search(query, top_k=top_k)
