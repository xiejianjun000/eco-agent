#!/usr/bin/env python3
"""门禁5：降级可观测性（对应 C1/D1）

mock embedding 服务超时 → search_hybrid 优雅降级为 BM25，
返回 vector_enabled=false，且日志有 WARN 记录。
"""
from __future__ import annotations

import logging
from pathlib import Path
from unittest import mock

import pytest

from _scripts.memory_tree import MemoryTree


@pytest.fixture()
def tree(tmp_path: Path) -> MemoryTree:
    mt = MemoryTree(db_path=tmp_path / "mem.db")
    for i in range(3):
        mt.create_node("case", f"锑渣节点{i}", f"冷水江锑渣处理{i}", tags=["env"])
    return mt


def test_vector_degrade_warns_and_marks(tree, caplog):
    with caplog.at_level(logging.WARNING, logger="memory_tree"), mock.patch("agent_core.hybrid_retrieval.EmbeddingClient") as MockEC, \
             mock.patch("agent_core.hybrid_retrieval.VectorStore") as MockVS:
        inst = MockEC.return_value
        inst.available.return_value = True
        inst.embed.side_effect = TimeoutError("embedding endpoint timeout")
        store = MockVS.return_value
        store.existing_ids.return_value = set()

        out = tree.search_hybrid("锑渣", max_results=5)

    # ① 降级后所有结果标记 vector_enabled=false
    assert out, "应返回 BM25 降级结果"
    assert all(n.get("vector_enabled") is False for n in out)
    assert all(n.get("channel") == "bm25" for n in out)
    # ② 有 WARN 日志
    assert any("向量检索降级" in r.getMessage() for r in caplog.records), \
        "降级应打 WARN 日志（可观测性门禁）"


def test_no_embedding_config_no_warn(tree, caplog):
    """未配置 embedding（available=False）→ 静默降级、不误报 WARN。"""
    with caplog.at_level(logging.WARNING, logger="memory_tree"), \
            mock.patch("agent_core.hybrid_retrieval.EmbeddingClient") as MockEC:
        MockEC.return_value.available.return_value = False
        out = tree.search_hybrid("锑渣", max_results=5)
    assert out and all(n.get("vector_enabled") is False for n in out)
    # 未配置是正常路径，不应有降级 WARN（只有"配置了但失败"才 WARN）
    assert not any("向量检索降级" in r.getMessage() for r in caplog.records)
