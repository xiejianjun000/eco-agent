#!/usr/bin/env python3
"""
test_ecobench_procedure.py — B2 执法程序类 RAG 补强的 mock 测试（不依赖远程服务器）

覆盖：
  - 程序关键词 → 程序法概念文件定位 locate_procedure_files（KB 真实路径）
  - 程序窗口截取 extract_procedure_window（锚定题干关键词所在条款）
  - retrieve_v2 对"执法程序"类别执行罚则+程序双段注入，非程序类不注入程序段
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from benchmarks.ecobench.run_ecobench import (  # noqa: E402
    PENALTY_WINDOW_CHARS,
    PROCEDURE_WINDOW_CHARS,
    RagRetriever,
    extract_procedure_window,
    locate_procedure_files,
)

PROC_FILE = "flowwiki/wiki/concepts/108-环境保护主管部门实施查封、扣押办法.md"
PENALTY_FILE = "flowwiki/wiki/concepts/75-生态环境行政处罚办法.md"

PROC_TEXT = (
    "# 环境保护主管部门实施查封、扣押办法\n\n"
    "## 第二章 实施程序\n"
    "第十条 实施查封、扣押应当由两名以上具有行政执法资格的环境行政执法人员实施，"
    "并出示执法身份证件。\n"
    "第十一条 实施查封、扣押前应当向环境保护主管部门负责人报告并经批准。\n"
    "第十二条 查封、扣押决定书应当当场交付排污者负责人或者受委托人签收。\n"
)
PENALTY_TEXT = (
    "# 生态环境行政处罚办法\n\n"
    "### 第五十九条 行政处罚决定书应当载明当事人的基本情况、违法事实和证据……\n"
)


def fake_call_tool_factory():
    reads = []

    def call_tool(server, tool, arguments):
        if tool == "kb_read":
            path = arguments.get("relative_path", "")
            reads.append(path)
            if path == PROC_FILE:
                return {"success": True, "text": PROC_TEXT}
            return {"success": True, "text": PENALTY_TEXT}
        if tool == "kb_search":
            return {"success": True, "text": f"📄 {PENALTY_FILE}\n"}
        return {"success": False, "error": "unknown"}

    call_tool.reads = reads
    return call_tool


def test_locate_procedure_files_keywords():
    files = locate_procedure_files("实施查封、扣押的程序要求是什么？")
    assert files and "查封" in files[0]
    assert locate_procedure_files("办案期限是如何规定的？") == [PENALTY_FILE]
    assert locate_procedure_files("移送司法机关的程序")  # 移送 → 行刑衔接
    assert locate_procedure_files("午饭吃什么？") == []


def test_extract_procedure_window_anchors_keyword():
    q = "查封、扣押决定书应当如何交付？"
    win = extract_procedure_window(PROC_TEXT, q, max_chars=200)
    assert "查封" in win and len(win) <= 200
    # 空文本 / 无锚点
    assert extract_procedure_window("", q) == ""
    assert extract_procedure_window("无关内容" * 50, "毫无关联的问题") .startswith("无关内容")


def test_retrieve_v2_dual_window_for_procedure():
    item = {
        "id": "EB33", "category": "执法程序",
        "question": "生态环境部门实施查封、扣押的程序要求是什么？",
        "required_citations": ["《行政强制法》第十八条"],
        "key_points": ["出示证件", "负责人批准"],
    }
    r = RagRetriever(call_tool=fake_call_tool_factory())
    hit = r.retrieve_v2(item)
    ctx = hit["context"]
    assert "【罚则条款参考】" in ctx and "【程序条款参考】" in ctx  # 双段注入
    assert "查封" in ctx
    assert len(ctx) <= PENALTY_WINDOW_CHARS + PROCEDURE_WINDOW_CHARS + 40
    assert any("查封" in f for f in hit["files"])  # 程序文件进检索清单


def test_retrieve_v2_no_procedure_segment_for_other_category():
    item = {
        "id": "EB01", "category": "法条引用",
        "question": "超标排放大气污染物的法律责任是什么？",
        "required_citations": [], "key_points": [],
    }
    r = RagRetriever(call_tool=fake_call_tool_factory())
    hit = r.retrieve_v2(item)
    assert "【程序条款参考】" not in hit["context"]
