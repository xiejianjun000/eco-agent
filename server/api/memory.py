#!/usr/bin/env python3
"""
server/api/memory.py — 记忆树 API

复用 _scripts.memory_tree.MemoryTree（SQLite + Obsidian 双向同步）。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger("eco.server.memory")

router = APIRouter()


def _memory_tree():
    from _scripts.memory_tree import MemoryTree

    return MemoryTree()


@router.get("/memory/nodes")
async def list_nodes(
    type: str | None = Query(default=None, description="节点类型过滤"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict:
    tree = _memory_tree()
    nodes = tree.list_nodes(type=type, limit=limit, offset=offset)
    return {"count": len(nodes), "nodes": nodes}


@router.get("/memory/hot")
async def hot_nodes(limit: int = Query(default=20, ge=1, le=100)) -> dict:
    tree = _memory_tree()
    return {"nodes": tree.get_hot_nodes(limit=limit)}


@router.get("/memory/search")
async def search_memory(
    q: str = Query(..., min_length=1, description="检索关键词"),
    type: str | None = Query(default=None),
    hybrid: bool = Query(default=False, description="BM25+向量混合检索"),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict:
    tree = _memory_tree()
    if hybrid:
        nodes = tree.search_hybrid(q, type=type)
    else:
        nodes = tree.search(q, type=type, max_results=limit)
    # 结果级 vector_enabled 标志：hybrid 且任一命中走向量通道才为 true（未配置 embedding 时 false）
    vector_enabled = hybrid and any(n.get("vector_enabled") for n in nodes)
    return {"query": q, "count": len(nodes), "vector_enabled": vector_enabled,
            "nodes": nodes[:limit]}


@router.get("/memory/nodes/{node_id}")
async def get_node(node_id: str) -> dict:
    tree = _memory_tree()
    node = tree.get_node(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="node not found")
    return node


@router.get("/memory/stats")
async def memory_stats() -> dict:
    tree = _memory_tree()
    return tree.get_stats()
