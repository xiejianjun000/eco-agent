"""LLM 客户端测试——mock httpx 层，不联网；验证重试/熔断/降级/自适应"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
import pytest
from agent_core.llm_client import LLMClient


class FakeResp:
    def __init__(self, status=200, content="回答内容", text=""):
        self.status_code = status
        self._content = content
        self.text = text or content

    def json(self):
        return {"choices": [{"message": {"content": self._content}}]}


@pytest.fixture
def client(monkeypatch):
    """未禁用、带 key 的客户端；sleep 置空避免真实退避等待"""
    monkeypatch.setenv("ECO_LLM_DISABLE", "")
    monkeypatch.setattr("time.sleep", lambda *a, **k: None)
    return LLMClient(api_key="sk-test", model="primary-model", fallback_model="fallback-model")


@pytest.fixture
def mock_http(monkeypatch):
    """拦截 httpx.post，返回可控的响应队列，记录所有请求"""
    calls = []
    state = {"queue": []}

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append({"url": url, "json": json, "headers": headers})
        item = state["queue"].pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr("httpx.post", fake_post)
    return state, calls


class TestLLMClient:
    def test_success_returns_content(self, client, mock_http):
        state, calls = mock_http
        state["queue"] = [FakeResp(200, "  成功回答  ")]
        out = client.chat([{"role": "user", "content": "hi"}])
        assert out == "成功回答"
        assert len(calls) == 1
        assert calls[0]["json"]["model"] == "primary-model"
        assert calls[0]["headers"]["Authorization"] == "Bearer sk-test"

    def test_500_retries_then_succeeds(self, client, mock_http):
        state, calls = mock_http
        state["queue"] = [FakeResp(500, "", "server error"), FakeResp(200, "重试成功")]
        out = client.chat([{"role": "user", "content": "hi"}])
        assert out == "重试成功"
        assert len(calls) == 2

    def test_400_temperature_adaptation(self, client, mock_http):
        """k2.x 仅接受 temperature=1：400 报错后自适应并缓存该约束"""
        state, calls = mock_http
        state["queue"] = [FakeResp(400, "", "invalid temperature"), FakeResp(200, "ok")]
        out = client.chat([{"role": "user", "content": "hi"}], temperature=0.3)
        assert out == "ok"
        assert calls[0]["json"]["temperature"] == 0.3
        assert calls[1]["json"]["temperature"] == 1
        assert client._temp_one_only is True

    def test_404_switches_to_fallback(self, client, mock_http):
        state, calls = mock_http
        state["queue"] = [FakeResp(404, "", "model not found"), FakeResp(200, "备用模型回答")]
        out = client.chat([{"role": "user", "content": "hi"}])
        assert out == "备用模型回答"
        assert calls[0]["json"]["model"] == "primary-model"
        assert calls[1]["json"]["model"] == "fallback-model"

    def test_single_chat_retries_up_to_max(self, client, mock_http):
        """单次 chat 失败必须重试满 MAX_RETRIES 次（每次间隔指数退避）"""
        state, calls = mock_http
        state["queue"] = [ConnectionError("网络断")] * 3
        assert client.chat([{"role": "user", "content": "hi"}]) is None
        assert len(calls) == 3, "单次 chat 必须重试满 3 次"

    def test_circuit_breaker_opens_after_max_failures(self, client, mock_http):
        """连续 3 次 chat 全部失败后熔断：available() 变 False，不再发出请求"""
        state, calls = mock_http
        state["queue"] = [ConnectionError("网络断")] * 9
        for _ in range(3):
            assert client.chat([{"role": "user", "content": "hi"}]) is None
        assert client._fail_count == 3
        assert client.available() is False, "连续失败必须触发熔断"
        calls_before = len(calls)
        assert client.chat([{"role": "user", "content": "hi"}]) is None
        assert len(calls) == calls_before, "熔断期间不得发出新请求"
        # 熔断窗口过后恢复
        client._circuit_open_until = 0
        assert client.available() is True

    def test_success_resets_circuit(self, client, mock_http):
        """一次成功必须清零失败计数（熔断恢复路径）"""
        state, calls = mock_http
        client._fail_count = 2
        state["queue"] = [FakeResp(200, "恢复")]
        assert client.chat([{"role": "user", "content": "hi"}]) == "恢复"
        assert client._fail_count == 0

    def test_disabled_by_env(self, monkeypatch, mock_http):
        monkeypatch.setenv("ECO_LLM_DISABLE", "1")
        c = LLMClient(api_key="sk-test")
        state, calls = mock_http
        state["queue"] = [FakeResp(200, "不应到达")]
        assert c.available() is False
        assert c.chat([{"role": "user", "content": "hi"}]) is None
        assert calls == []

    def test_no_api_key_unavailable(self, monkeypatch):
        monkeypatch.setenv("ECO_LLM_DISABLE", "")
        monkeypatch.delenv("KIMI_API_KEY", raising=False)
        c = LLMClient(api_key="")
        assert c.available() is False

    def test_empty_content_retries_with_larger_max_tokens(self, client, mock_http):
        """思考模型返回空内容 → 放大 max_tokens 重试且不计熔断"""
        state, calls = mock_http
        state["queue"] = [FakeResp(200, ""), FakeResp(200, "放大后有内容")]
        out = client.chat([{"role": "user", "content": "hi"}], max_tokens=512)
        assert out == "放大后有内容"
        assert calls[0]["json"]["max_tokens"] == 512
        assert calls[1]["json"]["max_tokens"] == 2048
        assert client.available() is True, "空内容重试不得计入熔断"
