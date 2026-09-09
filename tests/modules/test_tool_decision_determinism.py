#!/usr/bin/env python3
"""tests/modules/test_tool_decision_determinism.py — 工具决策温度收口

背景（实测缺陷，非假想）：
  同一句「你好」在**全新会话**下重复 3 次，结果是：
      第1次  3.1s  零工具，直接作答
      第2次  3.9s  零工具，直接作答
      第3次 31.0s  调了 3 个工具（air_quality_realtime + chart_render ×2）

  根因：两条工具决策路径都硬编码 temperature=0.7
      agent_core/llm_client.py  _call_chat_with_tools        (非流式)
      agent_core/llm_client.py  _call_chat_with_tools_stream (流式，Web 主用)
  而 server/api/chat.py 的 ChatRequest.temperature 字段从未被使用。

  工具「选哪个/要不要调」属于决策，不是创作 —— 靠采样会让同一问题
  时而查库时而空手作答，且直接影响耗时与配额消耗。

本文件锁死：工具决策路径必须用确定性低温，且可通过环境变量调整；
同时保留 kimi-k2.x 强制 temperature=1 的既有约束不被破坏。
"""

from __future__ import annotations

import agent_core.llm_client as LC
from agent_core.llm_client import LLMClient


class _Resp:
    status_code = 200

    @staticmethod
    def json():
        return {"choices": [{"message": {"role": "assistant", "content": "ok"},
                             "finish_reason": "stop"}]}

    text = ""


def _client(monkeypatch, model="deepseek-chat"):
    c = LLMClient.__new__(LLMClient)
    c._provider = {"default_model": model, "api_key_env": "X",
                   "base_url": "https://example.invalid/v1"}
    c._provider_name = "deepseek"
    c._api_key = "k"
    c._last_error = None
    monkeypatch.setattr(c, "_refresh_key", lambda: "k", raising=False)
    monkeypatch.setattr(c, "_record_usage", lambda *a, **kw: None, raising=False)
    return c


class _FakeHttpx:
    """替身 http 客户端：只记录出站 body，不发真实请求。"""

    def __init__(self, sink):
        self._sink = sink

    def post(self, _url, **kw):
        self._sink.append(kw.get("json") or {})
        return _Resp()


def _capture(monkeypatch, client):
    """拦住出站请求，返回记录 body 的列表。

    真实调用走实例属性 self._httpx.post（见 llm_client 内 _call_* 实现），
    因此替身必须挂在实例上，而不是模块级 httpx。
    """
    seen = []
    client._httpx = _FakeHttpx(seen)
    return seen


# ── 工具决策路径必须低温 ─────────────────────────────────────────
def test_tool_path_uses_deterministic_temperature(monkeypatch):
    """非流式工具路径不得再用 0.7。"""
    c = _client(monkeypatch)
    seen = _capture(monkeypatch, c)
    c._call_chat_with_tools("deepseek-chat", [{"role": "user", "content": "hi"}], [])
    assert seen, "未捕获到出站请求"
    temp = seen[0].get("temperature")
    assert temp == LC.TOOL_DECISION_TEMPERATURE
    assert temp <= 0.2, f"工具决策温度过高（{temp}），决策会不稳定"


def test_default_tool_temperature_is_zero_point_one():
    """默认值锁定：0.1（留极小随机性避免完全僵化，但足够稳定）。"""
    assert LC.TOOL_DECISION_TEMPERATURE == 0.1


def test_tool_temperature_is_configurable(monkeypatch):
    """可通过 ECO_TOOL_TEMPERATURE 调整（回退开关）。"""
    monkeypatch.setenv("ECO_TOOL_TEMPERATURE", "0.7")
    assert LC._tool_temperature() == 0.7
    monkeypatch.setenv("ECO_TOOL_TEMPERATURE", "0")
    assert LC._tool_temperature() == 0.0


def test_invalid_tool_temperature_falls_back_to_default(monkeypatch):
    """非法值不得让调用链崩掉，回落默认。"""
    monkeypatch.setenv("ECO_TOOL_TEMPERATURE", "不是数字")
    assert LC._tool_temperature() == LC.TOOL_DECISION_TEMPERATURE
    monkeypatch.setenv("ECO_TOOL_TEMPERATURE", "")
    assert LC._tool_temperature() == LC.TOOL_DECISION_TEMPERATURE


def test_out_of_range_tool_temperature_is_clamped(monkeypatch):
    """越界值收敛到合法区间 [0, 2]，不把非法值透传给上游。"""
    monkeypatch.setenv("ECO_TOOL_TEMPERATURE", "9")
    assert LC._tool_temperature() == 2.0
    monkeypatch.setenv("ECO_TOOL_TEMPERATURE", "-3")
    assert LC._tool_temperature() == 0.0


# ── 不得破坏 kimi-k2.x 强制 temperature=1 ────────────────────────
def test_kimi_k2_still_forced_to_one(monkeypatch):
    """kimi-k2.x 只接受 temperature=1，低温收口不能覆盖这条硬约束。"""
    c = _client(monkeypatch, model="kimi-k2.5")
    seen = _capture(monkeypatch, c)
    c._call_chat_with_tools("kimi-k2.5", [{"role": "user", "content": "hi"}], [])
    assert seen[0]["temperature"] == 1


def test_kimi_k2_forced_even_when_env_overrides(monkeypatch):
    """即便用户设了 ECO_TOOL_TEMPERATURE，kimi-k2.x 仍须为 1。"""
    monkeypatch.setenv("ECO_TOOL_TEMPERATURE", "0.9")
    c = _client(monkeypatch, model="kimi-k2-0905-preview")
    seen = _capture(monkeypatch, c)
    c._call_chat_with_tools("kimi-k2-0905-preview",
                            [{"role": "user", "content": "hi"}], [])
    assert seen[0]["temperature"] == 1


# ── 收口面：工具路径不得再出现裸 0.7 ─────────────────────────────
def test_no_bare_zero_point_seven_in_tool_paths():
    """源码层面守卫：两条工具路径不得再硬编码 0.7。

    盯的是「决策路径」，普通对话/补全路径允许保留 0.7。
    """
    import inspect

    for fn in (LLMClient._call_chat_with_tools,
               LLMClient._call_chat_with_tools_stream):
        src = inspect.getsource(fn)
        assert "_resolve_temperature(model, 0.7)" not in src, (
            f"{fn.__name__} 仍硬编码 0.7")
        assert "_tool_temperature()" in src, (
            f"{fn.__name__} 未走 _tool_temperature() 收口")
