#!/usr/bin/env python3
"""门禁1：SQL 注入防御（对应 B2）

向记忆树检索的 type 过滤器传入恶意 SQL 片段，断言参数化生效：
不返回全表、不抛语法错误（被当作字面量）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from _scripts.memory_tree import MemoryTree


@pytest.fixture()
def tree(tmp_path: Path) -> MemoryTree:
    mt = MemoryTree(db_path=tmp_path / "mem.db")
    for i in range(5):
        mt.create_node("case", f"节点{i}", f"内容{i}", tags=["env"])
    return mt


def test_type_filter_not_injectable(tree):
    """恶意 type 被参数化：不返回全部 5 条，也不抛 OperationalError。"""
    malicious = "' OR '1'='1"
    # 恶意串作为字面量 type 过滤，应匹配不到任何节点（type 值不等于该字符串）
    out = tree.search("内容", type=malicious, max_results=100)
    assert len(out) == 0, f"SQL 注入泄露了数据: {[r['id'] for r in out]}"


def test_type_filter_normal(tree):
    """正常 type 过滤仍可用。"""
    out = tree.search("内容", type="case", max_results=100)
    assert len(out) == 5


def test_type_filter_comment_injection(tree):
    """`--` 注释注入不改变语义。"""
    malicious = "case' --"
    out = tree.search("内容", type=malicious, max_results=100)
    # 被当作字面量 type，匹配不到（type != "case' --"）
    assert len(out) == 0
