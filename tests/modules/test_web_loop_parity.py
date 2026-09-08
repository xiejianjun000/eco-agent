#!/usr/bin/env python3
"""tests/modules/test_web_loop_parity.py — Web 主路径与 CLI 能力对等

背景（一个结构性缺陷，衍生出三处审计 ⚠️）：

  server/api/chat.py 的 Web/流式主循环不走 llm_client.chat_with_tools，
  而是直接调私有方法 client._call_chat_with_tools(_stream)。
  于是 chat_with_tools 内的两项能力在浏览器侧全部缺失：

    · _try_failover_provider()  —— 429/401/5xx 自动换 provider
    · record_decision()         —— SM3 决策链留痕

  后果很具体：CLI 用户遇到配额耗尽会自动切备用模型继续，
  浏览器用户只能看到一句错误文案；且整条浏览器侧的决策链是空的。

本文件锁死「Web 收口点 _call_llm_with_span 必须具备这两项能力」。
"""

from __future__ import annotations

import asyncio

import pytest

from server.api.chat import _call_llm_with_span


class _FakeTree:
    """最小 span 树替身：只记录 start/end，不做真实落盘。"""

    def __init__(self):
        self.ended: list[str] = []

    def start(self, *_a, **_kw):
        return "span-1"

    def end(self, _sid, **kw):
        self.ended.append(kw.get("finish_reason", ""))


class _FakeClient:
    """可编排的 LLM client 替身。

    calls 记录每次实际请求的 (model, stream)，用于断言降级确实换了模型、
    且沿用了原本的 stream 形态（而非退化成非流式）。
    """

    def __init__(self, *, results, recoverable=True, can_failover=True):
        self._results = list(results)      # 依次返回的 (msg, err)
        self._recoverable = recoverable
        self._can_failover = can_failover
        self._provider = {"default_model": "model-A"}
        self._provider_name = "provider-A"
        self._last_error = {"kind": "quota", "status": 429, "detail": "rate limit"}
        self.calls: list[tuple[str, bool]] = []
        self.failover_used = 0

    def _pop(self, mdl, stream):
        self.calls.append((mdl, stream))
        return self._results.pop(0) if self._results else (None, "exhausted")

    def _call_chat_with_tools(self, mdl, _messages, _tools):
        return self._pop(mdl, False)

    def _call_chat_with_tools_stream(self, mdl, _messages, _tools, on_chunk=None, on_reasoning=None):
        return self._pop(mdl, True)

    def _is_recoverable_error(self, _err):
        return self._recoverable

    def _try_failover_provider(self):
        if not self._can_failover:
            return False
        self.failover_used += 1
        self._provider = {"default_model": "model-B"}
        self._provider_name = "provider-B"
        return True

    def _friendly_error(self, _err):
        return "模型配额不足或被限流（HTTP 429）"


def _run(client, **kw):
    return asyncio.run(_call_llm_with_span(
        _FakeTree(), client, "", [{"role": "user", "content": "hi"}],
        [{"function": {"name": "t1"}}], 1, **kw))


# ── W2 provider failover ────────────────────────────────────────
def test_failover_switches_provider_on_recoverable_error():
    """首次 429 → 自动换 provider 重试并成功。"""
    c = _FakeClient(results=[(None, "HTTP 429"), ({"content": "ok"}, None)])
    msg, err = _run(c)
    assert c.failover_used == 1, "Web 路径未触发 provider 降级"
    assert msg == {"content": "ok"} and err is None
    assert [m for m, _ in c.calls] == ["model-A", "model-B"], "降级未换模型"


def test_failover_keeps_stream_shape():
    """降级重试必须沿用 stream=True，不退化成非流式。"""
    c = _FakeClient(results=[(None, "HTTP 429"), ({"content": "ok"}, None)])
    _run(c, stream=True)
    assert [s for _, s in c.calls] == [True, True], "降级把流式退化成了非流式"


def test_failover_emits_downgrade_notice_in_spec_format():
    """降级提示文案须与规格逐字一致。"""
    c = _FakeClient(results=[(None, "HTTP 429"), ({"content": "ok"}, None)])
    got: list[str] = []
    _run(c, stream=True, on_chunk=got.append)
    text = "".join(got)
    assert "[提示] 主模型不可用（" in text
    assert "已自动切换到备用模型 model-B 重试...\n" in text


def test_no_failover_when_error_not_recoverable():
    """不可恢复错误不应触发降级（避免无意义的二次消耗）。"""
    c = _FakeClient(results=[(None, "HTTP 400")], recoverable=False)
    msg, _err = _run(c)
    assert c.failover_used == 0
    assert msg is None
    assert len(c.calls) == 1


def test_no_failover_when_no_backup_provider():
    """没有可用备用 provider 时安静失败，不重复请求。"""
    c = _FakeClient(results=[(None, "HTTP 429")], can_failover=False)
    _run(c)
    assert len(c.calls) == 1


def test_failover_can_be_disabled_by_env(monkeypatch):
    """ECO_WEB_FAILOVER=0 为回退开关。"""
    monkeypatch.setenv("ECO_WEB_FAILOVER", "0")
    c = _FakeClient(results=[(None, "HTTP 429"), ({"content": "ok"}, None)])
    _run(c)
    assert c.failover_used == 0


def test_success_path_calls_once_only():
    """成功时不得有多余请求（防止把降级写成无条件重试）。"""
    c = _FakeClient(results=[({"content": "ok"}, None)])
    _run(c)
    assert len(c.calls) == 1
    assert c.failover_used == 0


# ── W1 record_decision 留痕 ─────────────────────────────────────
def test_records_decision_with_tool_calls(monkeypatch):
    """有 tool_calls → finish_reason=tool_calls 且带选中工具名。"""
    seen: list[dict] = []
    import agent_core.decisions as D

    monkeypatch.setattr(D, "record_decision", lambda **kw: seen.append(kw))
    c = _FakeClient(results=[({"tool_calls": [
        {"function": {"name": "query_air_quality"}}]}, None)])
    _run(c)
    assert len(seen) == 1, "Web 路径未写决策留痕"
    assert seen[0]["finish_reason"] == "tool_calls"
    assert seen[0]["selected_tools"] == ["query_air_quality"]
    assert seen[0]["candidate_tools"] == 1


def test_records_decision_stop_when_plain_answer(monkeypatch):
    """无 tool_calls → finish_reason=stop。"""
    seen: list[dict] = []
    import agent_core.decisions as D

    monkeypatch.setattr(D, "record_decision", lambda **kw: seen.append(kw))
    _run(_FakeClient(results=[({"content": "直接作答"}, None)]))
    assert seen[0]["finish_reason"] == "stop"
    assert seen[0]["selected_tools"] == []


def test_records_decision_error_when_call_failed(monkeypatch):
    """调用彻底失败 → finish_reason=error（CLI 侧原先无此分支）。"""
    seen: list[dict] = []
    import agent_core.decisions as D

    monkeypatch.setattr(D, "record_decision", lambda **kw: seen.append(kw))
    _run(_FakeClient(results=[(None, "boom")], recoverable=False))
    assert seen[0]["finish_reason"] == "error"


def test_records_provider_after_failover(monkeypatch):
    """降级后留痕须记录实际生效的 provider/model，而非原始的。"""
    seen: list[dict] = []
    import agent_core.decisions as D

    monkeypatch.setattr(D, "record_decision", lambda **kw: seen.append(kw))
    c = _FakeClient(results=[(None, "HTTP 429"), ({"content": "ok"}, None)])
    _run(c)
    assert seen[0]["model"] == "model-B"
    assert seen[0]["provider"] == "provider-B"


def test_decision_failure_never_breaks_main_flow(monkeypatch):
    """留痕抛异常不得影响主流程返回（旁路语义）。"""
    import agent_core.decisions as D

    def _boom(**_kw):
        raise RuntimeError("audit down")

    monkeypatch.setattr(D, "record_decision", _boom)
    msg, err = _run(_FakeClient(results=[({"content": "ok"}, None)]))
    assert msg == {"content": "ok"} and err is None


# ── 兼容性：不改变原有返回契约 ───────────────────────────────────
@pytest.mark.parametrize("results,want_msg", [
    ([({"content": "x"}, None)], {"content": "x"}),
    ([(None, "err")], None),
])
def test_return_contract_unchanged(results, want_msg):
    c = _FakeClient(results=results, recoverable=False)
    msg, _err = _run(c)
    assert msg == want_msg
