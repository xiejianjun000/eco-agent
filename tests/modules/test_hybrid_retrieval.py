#!/usr/bin/env python3
"""
test_hybrid_retrieval.py — B2 混合检索 mock 测试（不依赖真实 embedding 服务）

覆盖：
  - BM25 纯 Python 索引排序（中文 bigram）
  - RRF(k=60) 融合排序正确性
  - 向量通道：fake embedding 注入后走 hybrid；向量失败/无配置时优雅降级 BM25-only
  - VectorStore sqlite 幂等 upsert / 余弦排序
  - 工作区 relevant_history / relevant_context 来源标注与未命中回退
  - MemoryTree.search_hybrid 降级路径结构一致
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from agent_core.hybrid_retrieval import (  # noqa: E402
    BM25Index,
    EmbeddingClient,
    HybridRetriever,
    VectorStore,
    hybrid_search,
    rrf_fuse,
    tokenize,
)

DOCS = [
    {"id": "a", "text": "合力砖厂超标排放大气污染物，现场检查笔录已完成", "source": "note"},
    {"id": "b", "text": "按日连续处罚适用于拒不改正的违法排污行为", "source": "law"},
    {"id": "c", "text": "污水处理设施运行台账已核对，未发现异常", "source": "note"},
]


class FakeEmbedClient(EmbeddingClient):
    """伪造 embedding：按包含关键词给出可区分的确定性向量"""

    def __init__(self, fail: bool = False):
        self._fail = fail
        self.model = "fake-emb"

    def available(self):
        return not self._fail

    def embed(self, texts, timeout=30.0):
        if self._fail:
            return None
        out = []
        for t in texts:
            v = [0.0] * 8
            if "砖厂" in t or "大气" in t:
                v[0] = 1.0
            if "按日" in t or "处罚" in t:
                v[1] = 1.0
            if "污水" in t:
                v[2] = 1.0
            if not any(v):
                v[7] = 1.0
            out.append(v)
        return out


def test_tokenize_chinese_bigram():
    toks = tokenize("砖厂abc123")
    assert "砖厂" in toks and "abc123" in toks and "砖" in toks


def test_bm25_ranking():
    idx = BM25Index()
    idx.build([(d["id"], d["text"]) for d in DOCS])
    ranked = [d for d, _ in idx.score("砖厂大气超标排放")]
    assert ranked and ranked[0] == "a"
    assert "c" not in ranked  # 无共同词不得分


def test_rrf_fuse_order_and_k60():
    fused = rrf_fuse([["a", "b", "c"], ["b", "a"]], k=60)
    ids = [d for d, _ in fused]
    assert ids[0] == "a" and ids[1] == "b"
    # RRF 分 = 1/(60+rank) 求和
    assert abs(dict(fused)["b"] - (1 / 62 + 1 / 61)) < 1e-9


def test_vector_store_upsert_and_cosine(tmp_path):
    store = VectorStore(tmp_path / "vec.db")
    store.upsert("d1", [1.0, 0.0], source="s", text="t")
    store.upsert("d1", [0.0, 1.0], source="s", text="t")  # 幂等覆盖
    store.upsert("d2", [1.0, 0.0])
    rank = store.cosine_rank([1.0, 0.0])
    assert rank[0] == "d2"  # d1 已被覆盖为 [0,1]
    assert store.existing_ids(["d1", "dx"]) == {"d1"}


def test_hybrid_with_fake_vectors(tmp_path):
    r = HybridRetriever(namespace="t", vec_db=tmp_path / "v.db",
                        embed_client=FakeEmbedClient())
    r.index(DOCS)
    hits = r.search("砖厂大气", top_k=2)
    assert hits[0]["id"].endswith(":a")
    assert hits[0]["channel"] == "hybrid"  # 向量通道参与融合
    assert hits[0]["source"] == "note"     # 来源标注


def test_degrade_when_embed_fails(tmp_path):
    r = HybridRetriever(namespace="t", vec_db=tmp_path / "v.db",
                        embed_client=FakeEmbedClient(fail=True))
    r.index(DOCS)
    hits = r.search("按日连续处罚", top_k=2)
    assert hits and hits[0]["id"].endswith(":b")
    assert hits[0]["channel"] == "bm25"  # 优雅降级


def test_degrade_when_no_embedding_config(monkeypatch, tmp_path):
    # 默认 provider deepseek 无 embedding_model → 向量通道自动禁用
    monkeypatch.setenv("ECO_PROVIDER", "deepseek")
    monkeypatch.delenv("ECO_EMBED_PROVIDER", raising=False)
    monkeypatch.setenv("ECO_LLM_DISABLE", "1")
    r = HybridRetriever(namespace="t", vec_db=tmp_path / "v.db")
    assert not r.vector_enabled
    r.index(DOCS)
    hits = r.search("污水 台账", top_k=1)
    assert hits[0]["channel"] == "bm25"


def test_hybrid_search_adhoc(tmp_path):
    events = [{"kind": "user", "content": d["text"]} for d in DOCS]
    hits = hybrid_search(events, "大气 超标", top_k=1, namespace="adhoc-t",
                         embed=False, vec_db=tmp_path / "v.db")
    assert len(hits) == 1 and "砖厂" in hits[0]["text"]
    assert hits[0]["source"] == "user"


def test_workspace_relevant_context(tmp_path, monkeypatch):
    monkeypatch.setenv("ECO_LLM_DISABLE", "1")  # 强制 BM25-only
    from agent_core.workspace import WorkspaceManager
    mgr = WorkspaceManager(root=tmp_path / "ws")
    ws = mgr.create("合力砖厂检查")
    for i in range(6):
        ws.add_event("user", f"第{i+1}轮：检查记录")
    ws.add_event("law", "砖厂涉嫌违反《大气污染防治法》第九十九条 超标排放")
    ws.add_event("note", "按日连续处罚程序需先责令改正")
    mgr.open("合力砖厂检查")
    hits = ws.relevant_history("大气 超标 处罚条款", top_k=2)
    assert hits and hits[0]["channel"] == "bm25"
    ctx = ws.relevant_context("按日连续处罚 责令改正")
    assert "按日连续处罚" in ctx and "相关" in ctx  # 检索片段注入（带来源标注）
    # 未命中 → 空串（调用方回退摘要快照）
    assert ws.relevant_context("") == ""


def test_memory_tree_search_hybrid_degrade(tmp_path, monkeypatch):
    monkeypatch.setenv("ECO_LLM_DISABLE", "1")
    from _scripts.memory_tree import MemoryTree
    mt = MemoryTree(db_path=tmp_path / "mem.db")
    mt.create_node(type="case", title="砖厂大气超标案",
                   content="合力砖厂超标排放大气污染物", tags=["workspace"])
    mt.create_node(type="case", title="污水台账案",
                   content="污水处理台账核对", tags=["workspace"])
    out = mt.search_hybrid("大气 超标", max_results=2)
    assert out and out[0]["title"] == "砖厂大气超标案"
    assert out[0]["channel"] == "bm25" and "rrf_score" in out[0]
