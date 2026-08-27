#!/usr/bin/env python3
"""
tests/modules/test_eco_codex.py — 生态环境法典 skill 与检索工具测试

覆盖: 条文精确检索（阿拉伯/中文数字）、关键词检索、编章导航、
      LLM 工具表注册（statute_lookup/statute_search, L1）。
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

LOOKUP = ROOT / "ecoskills" / "eco-codex" / "scripts" / "lookup.py"


def _run(*args):
    r = subprocess.run([sys.executable, str(LOOKUP), *args], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_article_arabic():
    r = _run("article", "1054")
    assert r["num"] == 1054
    assert "五年内被发现" in r["text"]


def test_article_chinese():
    r = _run("article", "第一千二百四十二条")
    assert r["num"] == 1242
    assert "2026年8月15日起施行" in r["text"]
    assert "同时废止" in r["text"]


def test_article_full_ref():
    r = _run("article", "第1054条")
    assert r["num"] == 1054


def test_article_missing():
    r = _run("article", "99999")
    assert r["text"] is None
    assert "error" in r


def test_search_evasion():
    r = _run("search", "逃避监管")
    assert r["count"] >= 3
    assert any("暗管" in h["text"] for h in r["hits"])


def test_search_anri():
    r = _run("search", "按日连续")
    assert r["count"] >= 1
    assert any("按日连续处罚" in h["text"] for h in r["hits"])


def test_nav_structure():
    r = _run("nav")
    bians = r["bians"]
    assert len(bians) == 5
    assert bians[0]["name"] == "总则"
    assert bians[-1]["name"] == "法律责任和附则"


def test_bian_overview():
    r = _run("bian", "2")
    assert r["article_range"] == [148, 673]
    assert r["article_count"] == 526


def test_kb_completeness():
    """知识库完整性：五编文件 + 1242 条索引。"""
    kb = ROOT / "ecoskills" / "eco-codex" / "kb"
    files = list(kb.glob("第*编_*.md"))
    assert len(files) == 5
    index = json.loads((kb / "index.json").read_text(encoding="utf-8"))
    assert index["total_articles"] == 1242


def test_llm_tool_registered():
    """statute_lookup/statute_search 已注册进 LLM 可见工具表（L1 自动放行）。"""
    from agent_core.tools_registry import external_tool_overrides, get_tool_names

    names = get_tool_names()
    assert "statute_lookup" in names
    assert "statute_search" in names
    overrides = external_tool_overrides()
    assert overrides.get("statute_lookup") == "L1"
    assert overrides.get("statute_search") == "L1"


def test_execute_tool_l1_auto_allowed(monkeypatch):
    """execute_tool 路径：L1 工具自动放行并返回条文。"""
    import asyncio

    from agent_core.tools_registry import execute_tool

    monkeypatch.setenv("ECO_PERMISSION_GATE", "1")
    result = asyncio.run(execute_tool("statute_lookup", {"article": "1054"}))
    assert "五年内被发现" in result
