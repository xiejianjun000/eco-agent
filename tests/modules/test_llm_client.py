"""LLM 客户端测试——mock httpx 层，不联网；验证温度自适应/网关降级/错误链透传"""
import sys
import os
import json
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
def client(monkeypatch, tmp_path):
    """未禁用、带 kimi key 的客户端（ECO_PROVIDER=kimi）"""
    monkeypatch.setenv("ECO_LLM_DISABLE", "")
    monkeypatch.setenv("ECO_PROVIDER", "kimi")
    monkeypatch.setenv("KIMI_API_KEY", "sk-test")
    monkeypatch.delenv("GOVMCP_GATEWAY", raising=False)
    monkeypatch.delenv("GOVMCP_GATEWAY_KEY", raising=False)
    monkeypatch.setattr("time.sleep", lambda *a, **k: None)
    return LLMClient()


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


def _content(out: dict) -> str:
    return out["choices"][0]["message"]["content"]


class TestTemperatureAdaptation:
    def test_kimi_k2_forces_temperature_one(self, client, mock_http):
        """kimi-k2.x 只接受 temperature=1：payload 中必须被强制为 1"""
        state, calls = mock_http
        state["queue"] = [FakeResp(200, "ok")]
        client.chat([{"role": "user", "content": "hi"}], temperature=0.7)
        assert calls[0]["json"]["model"] == "kimi-k2.5"
        assert calls[0]["json"]["temperature"] == 1

    def test_resolve_temperature_prefix_match(self):
        assert LLMClient._resolve_temperature("kimi-k2.5", 0.3) == 1
        assert LLMClient._resolve_temperature("kimi-k2-0905-preview", 0.9) == 1
        assert LLMClient._resolve_temperature("Kimi-K2.5", 0.2) == 1
        assert LLMClient._resolve_temperature("deepseek-chat", 0.3) == 0.3
        assert LLMClient._resolve_temperature("moonshot-v1-8k", 0.5) == 0.5

    def test_non_kimi_model_keeps_temperature(self, monkeypatch, mock_http):
        monkeypatch.setenv("ECO_LLM_DISABLE", "")
        monkeypatch.setenv("ECO_PROVIDER", "deepseek")
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds")
        c = LLMClient()
        state, calls = mock_http
        state["queue"] = [FakeResp(200, "ok")]
        c.chat([{"role": "user", "content": "hi"}], temperature=0.3)
        assert calls[0]["json"]["temperature"] == 0.3

    def test_complete_uses_adapted_temperature(self, client, mock_http):
        """complete() 也收敛到同一 payload 构建入口"""
        state, calls = mock_http
        state["queue"] = [FakeResp(200, "  完成  ")]
        out = client.complete("hi", max_tokens=64)
        assert out == "完成"
        assert calls[0]["json"]["temperature"] == 1
        assert calls[0]["json"]["max_tokens"] == 64


class TestGatewayFallback:
    def test_gateway_preferred_when_configured(self, client, monkeypatch, mock_http):
        """配置 GOVMCP_GATEWAY 后优先走网关，且不再请求直连"""
        monkeypatch.setenv("GOVMCP_GATEWAY", "http://gw.local:9000/")
        monkeypatch.setenv("GOVMCP_GATEWAY_KEY", "gw-key")
        c = LLMClient()
        state, calls = mock_http
        state["queue"] = [FakeResp(200, "网关回答")]
        out = c.chat([{"role": "user", "content": "hi"}])
        assert _content(out) == "网关回答"
        assert len(calls) == 1
        assert calls[0]["url"] == "http://gw.local:9000/chat/completions"
        assert calls[0]["headers"]["Authorization"] == "Bearer gw-key"
        assert calls[0]["json"]["temperature"] == 1  # kimi-k2.5 自适应

    def test_gateway_failure_falls_back_to_direct(self, client, monkeypatch, mock_http):
        """网关失败降级 PROVIDERS 直连，错误链透传"""
        monkeypatch.setenv("GOVMCP_GATEWAY", "http://gw.local:9000")
        c = LLMClient()
        state, calls = mock_http
        state["queue"] = [ConnectionError("网关挂"), FakeResp(200, "直连回答")]
        out = c.chat([{"role": "user", "content": "hi"}])
        assert _content(out) == "直连回答"
        assert len(calls) == 2
        assert "gw.local" in calls[0]["url"]
        assert "moonshot.cn" in calls[1]["url"]

    def test_all_backends_fail_error_chain(self, client, monkeypatch, mock_http):
        """全部失败：返回降级消息 + 完整错误链"""
        monkeypatch.setenv("GOVMCP_GATEWAY", "http://gw.local:9000")
        c = LLMClient()
        state, calls = mock_http
        state["queue"] = [FakeResp(502, "", "bad gateway"), FakeResp(500, "", "server error")]
        out = c.chat([{"role": "user", "content": "hi"}])
        assert out.get("_error") is True
        assert "gateway(http://gw.local:9000): HTTP 502" in out["_error_detail"]
        assert "direct(kimi): HTTP 500" in out["_error_detail"]
        assert "[LLM unavailable" in _content(out)


class TestBasicBehavior:
    def test_success_returns_content(self, client, mock_http):
        state, calls = mock_http
        state["queue"] = [FakeResp(200, "  成功回答  ")]
        out = client.chat([{"role": "user", "content": "hi"}])
        assert _content(out) == "  成功回答  "
        assert len(calls) == 1
        assert calls[0]["json"]["model"] == "kimi-k2.5"
        assert calls[0]["headers"]["Authorization"] == "Bearer sk-test"

    def test_direct_failure_uses_kimi_fallback_for_non_kimi(self, monkeypatch, mock_http):
        """非 kimi provider 直连失败 → Kimi 直连兜底"""
        monkeypatch.setenv("ECO_LLM_DISABLE", "")
        monkeypatch.setenv("ECO_PROVIDER", "deepseek")
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds")
        monkeypatch.setenv("KIMI_API_KEY", "sk-kimi")
        c = LLMClient()
        state, calls = mock_http
        state["queue"] = [FakeResp(500, "", "boom"), FakeResp(200, "kimi兜底回答")]
        out = c.chat([{"role": "user", "content": "hi"}])
        assert _content(out) == "kimi兜底回答"
        assert "deepseek.com" in calls[0]["url"]
        assert "moonshot.cn" in calls[1]["url"]
        assert calls[1]["json"]["model"] == "kimi-k2.5"
        assert calls[1]["json"]["temperature"] == 1

    def test_disabled_by_env(self, monkeypatch, mock_http):
        monkeypatch.setenv("ECO_LLM_DISABLE", "1")
        monkeypatch.setenv("ECO_PROVIDER", "kimi")
        monkeypatch.setenv("KIMI_API_KEY", "sk-test")
        c = LLMClient()
        state, calls = mock_http
        state["queue"] = [FakeResp(200, "不应到达")]
        assert c.available() is False
        out = c.chat([{"role": "user", "content": "hi"}])
        assert out.get("_error") is True
        assert calls == []

    def test_no_api_key_unavailable(self, monkeypatch):
        monkeypatch.setenv("ECO_LLM_DISABLE", "")
        monkeypatch.setenv("ECO_PROVIDER", "openai")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        c = LLMClient()
        # .env 文件里无 OPENAI_API_KEY 时不可用（若本机 .env 恰好有则跳过）
        if c._api_key:
            pytest.skip("local ~/.eco/.env provides OPENAI_API_KEY")
        assert c.available() is False

    def test_stats_track_calls_and_errors(self, client, mock_http):
        state, calls = mock_http
        state["queue"] = [FakeResp(200, "ok"), FakeResp(500, "", "err"), FakeResp(500, "", "err")]
        client.chat([{"role": "user", "content": "hi"}])
        client.chat([{"role": "user", "content": "hi"}])
        stats = client.get_stats()
        assert stats["calls"] == 2
        assert stats["errors"] == 1
        assert stats["provider"] == "kimi"
        assert stats["has_api_key"] is True


# ═══════════════════════════════════════════════════════════════
# 真流式（SSE）chat_with_tools 测试
# ═══════════════════════════════════════════════════════════════

class FakeStreamResp:
    """模拟 httpx.stream 的上下文管理器响应，按行吐出 SSE 数据"""

    def __init__(self, lines=(), status=200, err_text=""):
        self.status_code = status
        self._lines = list(lines)
        self._err_text = err_text

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def iter_lines(self):
        return iter(self._lines)

    def read(self):
        return self._err_text.encode("utf-8")


def _sse(obj) -> str:
    return "data: " + json.dumps(obj, ensure_ascii=False)


@pytest.fixture
def mock_stream(monkeypatch):
    """拦截 httpx.stream，返回可控的 SSE 响应队列，记录所有请求体"""
    calls = []
    state = {"queue": []}

    def fake_stream(method, url, headers=None, json=None, timeout=None):
        calls.append({"method": method, "url": url, "json": json, "headers": headers})
        item = state["queue"].pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr("httpx.stream", fake_stream)
    return state, calls


class TestRealStreaming:
    def test_stream_content_chunks_arrive_incrementally(self, client, mock_stream):
        """真流式：content delta 逐段即时回调，而非整块切片回放"""
        state, calls = mock_stream
        state["queue"] = [FakeStreamResp([
            _sse({"choices": [{"delta": {"content": "你好"}}]}),
            _sse({"choices": [{"delta": {"content": "，世界"}}]}),
            _sse({"choices": [{"delta": {"content": "！"}}],
                  "usage": {"prompt_tokens": 5, "completion_tokens": 3}}),
            "data: [DONE]",
        ])]
        chunks = []
        result = client.chat_with_tools(
            [{"role": "user", "content": "hi"}], tools=[],
            on_chunk=chunks.append, stream=True)
        assert result == "你好，世界！"
        assert chunks == ["你好", "，世界", "！"]  # 逐段到达，非 20 字切片回放
        assert calls[0]["json"]["stream"] is True

    def test_stream_payload_stream_true_and_kimi_temp_one(self, client, mock_stream):
        """payload 必须 stream=True，且 kimi-k2.x temperature 强制为 1"""
        state, calls = mock_stream
        state["queue"] = [FakeStreamResp([
            _sse({"choices": [{"delta": {"content": "ok"}}]}),
            "data: [DONE]",
        ])]
        client.chat_with_tools([{"role": "user", "content": "hi"}], tools=[],
                               on_chunk=lambda c: None, stream=True)
        assert calls[0]["json"]["stream"] is True
        assert calls[0]["json"]["model"] == "kimi-k2.5"
        assert calls[0]["json"]["temperature"] == 1

    def test_stream_tool_calls_assembled_by_index(self, client, mock_stream):
        """tool_calls delta 按 index 拼装：id/name 一次到达，arguments 分片累积"""
        state, calls = mock_stream
        state["queue"] = [FakeStreamResp([
            _sse({"choices": [{"delta": {"tool_calls": [
                {"index": 0, "id": "call_1", "type": "function",
                 "function": {"name": "search_regulation", "arguments": ""}}]}}]}),
            _sse({"choices": [{"delta": {"tool_calls": [
                {"index": 0, "function": {"arguments": "{\"key"}}]}}]}),
            _sse({"choices": [{"delta": {"tool_calls": [
                {"index": 1, "id": "call_2", "type": "function",
                 "function": {"name": "query_air_quality", "arguments": "{\"city\":\"北京\"}"}}]}}]}),
            _sse({"choices": [{"delta": {"tool_calls": [
                {"index": 0, "function": {"arguments": "word\":\"大气\"}"}}]}}]}),
            "data: [DONE]",
        ])]
        msg, err = client._call_chat_with_tools_stream("kimi-k2.5", [{"role": "user", "content": "hi"}], [])
        assert err is None
        tcs = msg["tool_calls"]
        assert [tc["id"] for tc in tcs] == ["call_1", "call_2"]  # 按 index 排序
        assert tcs[0]["function"]["name"] == "search_regulation"
        assert tcs[0]["function"]["arguments"] == "{\"keyword\":\"大气\"}"
        assert tcs[1]["function"]["name"] == "query_air_quality"
        assert json.loads(tcs[1]["function"]["arguments"]) == {"city": "北京"}

    def test_stream_429_failover_to_deepseek_streaming(self, monkeypatch, mock_stream):
        """429 → DeepSeek 流式降级：第二次请求仍为 stream=True 且打到 deepseek"""
        monkeypatch.setenv("ECO_LLM_DISABLE", "")
        monkeypatch.setenv("ECO_PROVIDER", "kimi")
        monkeypatch.setenv("KIMI_API_KEY", "sk-kimi")
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds")
        monkeypatch.delenv("GOVMCP_GATEWAY", raising=False)
        c = LLMClient()
        state, calls = mock_stream
        state["queue"] = [
            FakeStreamResp(status=429, err_text='{"error":{"message":"rate limit"}}'),
            FakeStreamResp([
                _sse({"choices": [{"delta": {"content": "降级回答"}}]}),
                "data: [DONE]",
            ]),
        ]
        chunks = []
        result = c.chat_with_tools([{"role": "user", "content": "hi"}], tools=[],
                                   on_chunk=chunks.append, stream=True)
        assert result == "降级回答"
        assert "降级回答" in chunks
        assert len(calls) == 2
        assert "moonshot.cn" in calls[0]["url"]
        assert "deepseek.com" in calls[1]["url"]
        assert calls[1]["json"]["stream"] is True
        assert calls[1]["json"]["model"] == "deepseek-chat"

    def test_stream_usage_recorded(self, client, mock_stream, tmp_path, monkeypatch):
        """流式路径同样记录 usage 统计"""
        stats_file = tmp_path / "stats.jsonl"
        monkeypatch.setattr("agent_core.llm_client.STATS_FILE", stats_file)
        state, calls = mock_stream
        state["queue"] = [FakeStreamResp([
            _sse({"choices": [{"delta": {"content": "ok"}}]}),
            _sse({"choices": [], "usage": {"prompt_tokens": 11, "completion_tokens": 7}}),
            "data: [DONE]",
        ])]
        client.chat_with_tools([{"role": "user", "content": "hi"}], tools=[],
                               on_chunk=lambda c: None, stream=True)
        rec = json.loads(stats_file.read_text(encoding="utf-8").strip().splitlines()[-1])
        assert rec["prompt_tokens"] == 11
        assert rec["completion_tokens"] == 7
        assert rec["ok"] is True


def test_lazy_api_key_refresh_self_heals():
    """单例构造早于环境变量注入时，后续调用惰性重读 Key 自愈
    （修复 'no api key (provider not configured)' 瞬时故障类）。"""
    import os

    from agent_core.llm_client import LLMClient

    saved = os.environ.pop("DEEPSEEK_API_KEY", None)
    try:
        c = LLMClient()  # 无 Key 构造（模拟 envboot 之前的导入期构造）
        assert c._api_key == ""
        os.environ["DEEPSEEK_API_KEY"] = "sk-lazy-test"
        try:
            assert c._refresh_key() == "sk-lazy-test"
            assert c._api_key == "sk-lazy-test"
            # conftest 强制 ECO_LLM_DISABLE=1，只验证 key 自愈本身
            saved_disabled = c._disabled
            c._disabled = False
            try:
                assert c.available() is True
            finally:
                c._disabled = saved_disabled
        finally:
            del os.environ["DEEPSEEK_API_KEY"]
    finally:
        if saved is not None:
            os.environ["DEEPSEEK_API_KEY"] = saved
