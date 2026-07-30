#!/usr/bin/env python3
"""
test_ecobench_rag.py — EcoBench RAG 检索注入流程的 mock 测试（不依赖远程服务器）

覆盖：
  - 主题词提取 extract_query_terms
  - kb_search 返回文本解析 parse_kb_search_files
  - RagRetriever.retrieve 的 search→read 流程（注入 fake call_tool）
  - answer_question 在 RAG 模式下把参考资料注入提示词（fake LLM client）
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from benchmarks.ecobench.run_ecobench import (  # noqa: E402
    RagRetriever,
    answer_question,
    extract_query_terms,
    parse_kb_search_files,
)

KB_SEARCH_TEXT = (
    "🔍 搜索 '大气' — 找到 2 条:\n\n"
    "📄 laws/大气污染防治法.md\n"
    "18:第九十九条 超标排放大气污染物...\n\n"
    "📄 flowwiki/wiki/skills/Skill_12.md\n"
    "18:related_laws: [\"[[大气污染防治法]]\"]\n"
)

KB_READ_TEXT = "《大气污染防治法》第九十九条：超过大气污染物排放标准排放大气污染物的，责令改正……"


def make_fake_call_tool():
    calls = []

    def call_tool(server, tool, arguments):
        calls.append((tool, arguments))
        if tool == "kb_search":
            if "超时词" in arguments.get("query", ""):
                return {"success": False, "error": "timeout"}
            return {"success": True, "text": KB_SEARCH_TEXT}
        if tool == "kb_read":
            return {"success": True, "text": KB_READ_TEXT}
        return {"success": False, "error": "unknown tool"}

    call_tool.calls = calls
    return call_tool


class FakeClient:
    """记录收到的 prompt，返回固定答案"""

    def __init__(self):
        self.prompts = []

    def available(self):
        return True

    def complete(self, prompt, system=None, max_tokens=1024):
        self.prompts.append(prompt)
        return "依据《大气污染防治法》第九十九条处理。"


def test_extract_query_terms_hit():
    terms = extract_query_terms("企业向大气超标排放污染物，应依据哪部法律查处？")
    assert terms[0] == "大气"
    assert "超标排放" in terms


def test_extract_query_terms_fallback():
    terms = extract_query_terms("某完全无关的题干xyz")
    assert terms == ["某完全无关的题干"]  # 兜底：题干前8字


def test_parse_kb_search_files():
    files = parse_kb_search_files(KB_SEARCH_TEXT)
    assert files == ["laws/大气污染防治法.md", "flowwiki/wiki/skills/Skill_12.md"]
    assert parse_kb_search_files("") == []


def test_retriever_retrieve_flow():
    fake = make_fake_call_tool()
    r = RagRetriever(call_tool=fake)
    hit = r.retrieve("企业向大气超标排放污染物怎么处理？")
    assert hit["files"] == ["laws/大气污染防治法.md", "flowwiki/wiki/skills/Skill_12.md"]
    assert "第九十九条" in hit["context"]          # kb_read 原文注入
    assert "检索命中摘要" in hit["context"]          # kb_search 摘要注入
    tools = [c[0] for c in fake.calls]
    assert "kb_search" in tools and "kb_read" in tools


def test_retriever_search_failure_degrades():
    def failing(server, tool, arguments):
        return {"success": False, "error": "timeout"}

    r = RagRetriever(call_tool=failing)
    hit = r.retrieve("大气排放怎么处理？")
    assert hit["files"] == [] and hit["context"] == ""


def test_answer_question_rag_injects_context():
    fake = make_fake_call_tool()
    retriever = RagRetriever(call_tool=fake)
    client = FakeClient()
    item = {"id": "EB01", "question": "企业向大气超标排放污染物，应依据哪条查处？"}
    ans, files = answer_question(client, item, mock=False, retriever=retriever)
    assert "第九十九条" in ans
    assert files  # 检索文件清单被记录
    prompt = client.prompts[0]
    assert "【参考资料】" in prompt and KB_READ_TEXT in prompt  # 注入参考资料
    assert item["question"] in prompt


def test_answer_question_baseline_prompt_unchanged():
    """基线模式（无 retriever）提示词保持原样，保证对照公平"""
    client = FakeClient()
    item = {"id": "EB01", "question": "企业向大气超标排放污染物，应依据哪条查处？"}
    ans, files = answer_question(client, item, mock=False)
    assert files == []
    assert client.prompts[0] == item["question"]
    assert ans


def test_answer_question_mock_mode():
    ans, files = answer_question(None, {"id": "X", "question": "q"}, mock=True)
    assert ans.startswith("[mock]") and files == []
