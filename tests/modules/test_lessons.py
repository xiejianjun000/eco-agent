#!/usr/bin/env python3
"""
tests/modules/test_lessons.py — 对话教训自动沉淀（自愈闭环）测试
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from agent_core.lessons import LessonStore, extract_lesson  # noqa: E402


def test_extract_on_failure(tmp_path):
    lesson = extract_lesson(
        "查中央生态环境保护督察工作规定",
        "官网未找到该文件，多个路径404。",
        ["web_fetch", "web_fetch"])
    assert lesson is not None
    assert "web_fetch" in lesson["lesson"]


def test_no_extract_on_success(tmp_path):
    lesson = extract_lesson("今天天气", "多云转晴，27度。", ["web_fetch"])
    assert lesson is None


def test_no_extract_without_tools(tmp_path):
    lesson = extract_lesson("查文件", "没找到。", [])
    assert lesson is None


def test_store_roundtrip(tmp_path):
    store = LessonStore(tmp_path / "l.jsonl")
    store.add({"keywords": ["督察", "规定"], "lesson": "坑1", "source": "auto", "when": 0})
    hits = store.search("督察规定相关问题")
    assert len(hits) == 1
    assert hits[0]["lesson"] == "坑1"


def test_search_no_false_positive(tmp_path):
    store = LessonStore(tmp_path / "l.jsonl")
    store.add({"keywords": ["督察", "规定"], "lesson": "坑1", "source": "auto", "when": 0})
    assert store.search("天气空气质量") == []
