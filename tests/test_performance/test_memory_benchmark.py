#!/usr/bin/env python3
"""门禁4：检索性能基准（对应 A1）

注入 2000 条节点，验证 BM25 索引缓存生效：热缓存检索 P95 < 500ms。
（10000 条的完整压测标为 slow，CI 默认跳过，见 test_memory_benchmark_slow）
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from _scripts.memory_tree import MemoryTree

N = 2000
LATENCY_BUDGET_S = 0.5  # 热缓存检索预算（500ms）


@pytest.fixture()
def tree(tmp_path: Path) -> MemoryTree:
    mt = MemoryTree(db_path=tmp_path / "mem.db")
    for i in range(N):
        mt.create_node(
            "case", f"节点{i} 秸秆禁烧规定", f"禁止露天焚烧秸秆，违者罚款。第{i}条测试数据。", tags=["env/air"], score=i % 100
        )
    return mt


def test_warm_search_latency(tree):
    # 冷查询：建立 BM25 索引（一次性成本，不计入预算）
    tree.search("秸秆禁烧", max_results=10)

    # 热查询：应命中缓存，P95 < 500ms
    queries = ["秸秆禁烧", "焚烧秸秆", "锑渣", "排污许可", "大气污染"]
    lat = []
    for q in queries:
        t = time.perf_counter()
        tree.search(q, max_results=10)
        lat.append(time.perf_counter() - t)
    lat.sort()
    p95 = lat[-1]
    assert p95 < LATENCY_BUDGET_S, (
        f"热缓存检索 P95 {p95 * 1000:.0f}ms 超出预算 {LATENCY_BUDGET_S * 1000:.0f}ms（索引缓存失效？）"
    )


def test_cache_invalidated_on_write(tree):
    """写入后缓存置空，下次检索仍正确（不返回脏数据）。"""
    tree.search("锑渣", max_results=10)  # 建缓存
    new_id = tree.create_node("case", "锑渣新节点", "冷水江锑渣日处理300吨", tags=["env"])
    out = tree.search("锑渣", max_results=20)
    ids = {n["id"] for n in out}
    assert new_id["id"] in ids, "写入后缓存未失效，检索漏了新节点"
