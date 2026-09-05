#!/usr/bin/env python3
"""
test_ecobench_resilience.py — EcoBench 三修（时限/重试/provider 切换）的 mock 测试

覆盖：
  1. 注入长度上限 RAG_MAX_CONTEXT_CHARS = 1500（条款窗口优先）
  2. 单题 90s 时限 + 失败重试 1 次后仍失败才计 error
  3. 429/余额类错误自动切换备用 provider，切换记录；两家都不可用则中止
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from agent_core.llm_client import LLMClient  # noqa: E402
from benchmarks.ecobench.run_ecobench import (  # noqa: E402
    BACKUP_PROVIDERS,
    LLM_CALL_TIMEOUT,
    PER_QUESTION_TIMEOUT,
    RAG_MAX_CONTEXT_CHARS,
    answer_question,
    extract_article_sections,
    new_bench_state,
    try_failover,
)

ITEM = {"id": "EB01", "category": "法条引用", "question": "企业向大气超标排放污染物，应依据哪条查处？"}


class FakeClient:
    """按脚本作答的 fake LLM client（脚本元素：答案 str / "" 失败 / None 由超时模拟）"""

    def __init__(self, script, provider="deepseek", error=None, switchable=True, clear_error_on_switch=True):
        self.script = list(script)
        self.calls = 0
        self._provider_name = provider
        self._error = error
        self.switched_to = []
        self._switchable = switchable
        self._clear_error = clear_error_on_switch

    def available(self):
        return True

    @property
    def last_error(self):
        return self._error

    def switch_provider(self, name):
        if not self._switchable:
            return False
        self._provider_name = name
        self.switched_to.append(name)
        if self._clear_error:
            self._error = None
        return True

    def complete(self, prompt, system=None, max_tokens=1024, timeout=90.0):
        self.calls += 1
        return self.script.pop(0) if self.script else ""


# ── 1) 注入长度 1500 ────────────────────────────────────


def test_context_cap_is_1500():
    assert RAG_MAX_CONTEXT_CHARS == 1500


def test_article_window_priority_over_file_head():
    """目标条款在文件尾部时，条款窗口（±1 条）优先于文件头"""
    head = "文件头无关内容。" * 200
    tail = "### 第九十八条\n\n前一条。\n\n### 第九十九条\n\n目标条款正文。\n\n### 第一百条\n\n后一条。"
    snippet, hit = extract_article_sections(head + "\n\n" + tail, [99], max_chars=1500)
    assert hit == [99]
    assert "目标条款正文" in snippet
    assert "前一条。" in snippet and "后一条。" in snippet  # ±1 条上下文保留
    assert "文件头无关内容" not in snippet  # 不是文件头截断
    assert len(snippet) <= 1500


# ── 2) 时限与重试 ───────────────────────────────────────


def test_timeouts_are_90s():
    assert PER_QUESTION_TIMEOUT == 90.0
    assert LLM_CALL_TIMEOUT == 90.0


def test_retry_once_then_success():
    state = new_bench_state()
    client = FakeClient(
        ["", "依据《大气污染防治法》第九十九条。"], error={"kind": "network", "status": None, "detail": "reset"}
    )
    ans, _, _ = answer_question(client, ITEM, mock=False, state=state)
    assert "第九十九条" in ans
    assert client.calls == 2 and state["retries"] == 1 and state["errors"] == 0


def test_retry_once_then_error():
    state = new_bench_state()
    client = FakeClient(["", ""], error={"kind": "http", "status": 500, "detail": "boom"})
    ans, _, _ = answer_question(client, ITEM, mock=False, state=state)
    assert ans.startswith("[error]")
    assert client.calls == 2 and state["retries"] == 1 and state["errors"] == 1


def test_timeout_retry_then_error(monkeypatch):
    """墙钟超时：重试 1 次后仍超时计 error，timeouts=2"""
    import benchmarks.ecobench.run_ecobench as m

    monkeypatch.setattr(m, "_call_with_timeout", lambda c, q, timeout=None: None)
    state = new_bench_state()
    client = FakeClient([], error=None)
    ans, _, _ = answer_question(client, ITEM, mock=False, state=state)
    assert ans.startswith("[error] timeout")
    assert state["timeouts"] == 2 and state["retries"] == 1 and state["errors"] == 1


# ── 3) 429/余额切换 ────────────────────────────────────


def test_quota_error_switches_provider_and_records():
    state = new_bench_state()
    client = FakeClient(
        ["", "依据《大气污染防治法》第九十九条。"],
        provider="deepseek",
        error={"kind": "quota", "status": 429, "detail": "rate limit"},
    )
    ans, _, _ = answer_question(client, ITEM, mock=False, state=state)
    assert "第九十九条" in ans
    assert client.switched_to == ["kimi"]
    assert len(state["switches"]) == 1
    sw = state["switches"][0]
    assert sw["from"] == "deepseek" and sw["to"] == "kimi" and sw["question"] == "EB01"


def test_both_providers_down_aborts():
    """备用 provider 也无密钥/切换失败 → 置 aborted，已得题目保留（由主循环 break）"""
    state = new_bench_state()
    client = FakeClient(
        [""], provider="deepseek", error={"kind": "quota", "status": 402, "detail": "Insufficient Balance"}, switchable=False
    )
    ans, _, _ = answer_question(client, ITEM, mock=False, state=state)
    assert ans.startswith("[error] aborted")
    assert state["aborted"] is True and "EB01" in state["abort_reason"]


def test_no_double_switch_back():
    """备用 provider 也 429 时不再切回原 provider，直接中止"""
    state = new_bench_state()
    client = FakeClient(
        ["", ""],
        provider="deepseek",
        error={"kind": "quota", "status": 429, "detail": "rate limit"},
        clear_error_on_switch=False,
    )  # 备用 provider 同样 429
    ans, _, _ = answer_question(client, ITEM, mock=False, state=state)
    assert ans.startswith("[error] aborted")
    assert client.switched_to == ["kimi"]  # 只切一次
    assert state["aborted"] is True


def test_try_failover_no_backup_for_unknown_provider():
    state = new_bench_state()
    client = FakeClient([], provider="openai")
    assert try_failover(client, "EB01", state) is False
    assert BACKUP_PROVIDERS == {"deepseek": "kimi", "kimi": "deepseek"}


# ── LLMClient 层 ───────────────────────────────────────


def test_llm_client_quota_detection():
    assert LLMClient._is_quota_error(429, "")
    assert LLMClient._is_quota_error(402, "")
    assert LLMClient._is_quota_error(400, "Insufficient Balance")
    assert LLMClient._is_quota_error(500, "rate_limit_exceeded")
    assert not LLMClient._is_quota_error(500, "internal error")


def test_llm_client_switch_provider():
    c = LLMClient.__new__(LLMClient)  # 跳过文件读取，手工构造
    c._env = {"DEEPSEEK_API_KEY": "k1", "KIMI_API_KEY": "k2"}
    c._provider_name = "deepseek"
    from agent_core.llm_client import PROVIDERS

    c._provider = PROVIDERS["deepseek"]
    c._api_key = "k1"
    c._last_error = {"kind": "quota"}
    assert c.switch_provider("kimi") is True
    assert c._provider_name == "kimi" and c._api_key == "k2" and c.last_error is None
    assert c.switch_provider("nonexistent") is False
