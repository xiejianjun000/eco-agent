"""推理流采集测试：deepseek-reasoner/v4 系列的 reasoning_content →
msg._reasoning → chat 循环 think 事件（DSH Think 流）。"""


from agent_core.llm_client import LLMClient


class FakeResp:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload


def _client_with_key(monkeypatch):
    monkeypatch.setenv("ECO_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    c = LLMClient()
    return c


class FakePost:
    def __init__(self, payload):
        self.payload = payload

    def __call__(self, url, headers=None, json=None, timeout=None):
        return FakeResp(200, self.payload)


def test_non_stream_captures_reasoning(monkeypatch):
    c = _client_with_key(monkeypatch)
    c._httpx = type("H", (), {"post": FakePost({
        "choices": [{"message": {"role": "assistant", "content": "答案",
                                 "reasoning_content": "这是真实推理流"}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    })})()
    msg, err = c._call_chat_with_tools("deepseek-reasoner",
                                       [{"role": "user", "content": "hi"}], [])
    assert err is None
    assert msg["_reasoning"] == "这是真实推理流"
    assert msg["content"] == "答案"


class FakeStream:
    status_code = 200

    def __init__(self, chunks):
        self._chunks = chunks

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def iter_lines(self):
        return self._chunks


def test_stream_captures_reasoning_chunks(monkeypatch):
    c = _client_with_key(monkeypatch)
    lines = [
        'data: {"choices":[{"delta":{"reasoning_content":"推理A"}}]}',
        'data: {"choices":[{"delta":{"reasoning_content":"推理B"}}]}',
        'data: {"choices":[{"delta":{"content":"答案"}}]}',
        'data: [DONE]',
    ]
    c._httpx = type("H", (), {"stream": lambda *a, **k: FakeStream(lines)})()
    chunks = []
    msg, err = c._call_chat_with_tools_stream(
        "deepseek-reasoner", [{"role": "user", "content": "hi"}], [],
        on_chunk=chunks.append)
    assert err is None
    assert msg["_reasoning"] == "推理A推理B"
    assert "".join(chunks) == "答案"


def test_reasoner_model_accepted_without_tools(monkeypatch):
    """reasoner 模式下 tools=[] 也走同一路径（不强制函数调用）。"""
    c = _client_with_key(monkeypatch)
    captured = {}

    def fake_post(self, url, headers=None, json=None, timeout=None):
        captured["body"] = json
        return FakeResp(200, {"choices": [{"message": {"role": "assistant",
                                                       "content": "直接回答",
                                                       "reasoning_content": "推理"}}],
                              "usage": {}})

    c._httpx = type("H", (), {"post": fake_post})()
    msg, err = c._call_chat_with_tools("deepseek-reasoner",
                                       [{"role": "user", "content": "hi"}], [])
    assert err is None and msg["_reasoning"] == "推理"
    assert "tools" not in captured["body"] or captured["body"].get("tools") in (None, [])
