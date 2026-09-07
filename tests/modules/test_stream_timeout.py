"""流式/整轮超时护栏回归测试。

背景：审计链实测单轮 12424s（3.5 小时）与 2055s 未收尾。
根因是 _call_chat_with_tools_stream 的 `for line in resp.iter_lines()`
没有任何总时长或空闲保护——httpx timeout 只管连接与单次读取间隔，
上游持续缓慢吐字节即可无限挂起。
"""
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))


class _FakeResp:
    """模拟持续吐字节但永不结束的 SSE 流。"""

    status_code = 200

    def __init__(self, gap: float, n: int = 10000):
        self._gap = gap
        self._n = n

    def iter_lines(self):
        for _ in range(self._n):
            time.sleep(self._gap)
            yield b'data: {"choices":[{"delta":{"content":"x"}}]}'

    def read(self):
        return b""

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeHttpx:
    def __init__(self, gap):
        self._gap = gap

    def stream(self, *a, **kw):
        return _FakeResp(self._gap)


def _client(total, idle):
    os.environ["ECO_STREAM_TOTAL_TIMEOUT"] = str(total)
    os.environ["ECO_STREAM_IDLE_TIMEOUT"] = str(idle)
    for m in [m for m in sys.modules if m.startswith("agent_core.llm_client")]:
        del sys.modules[m]
    import agent_core.llm_client as lc
    return lc


def test_stream_total_wall_clock_guard():
    """持续快速吐字节 → 必须被整体墙钟拦下，而不是无限跑。"""
    lc = _client(total=1.0, idle=60)
    c = lc.LLMClient.__new__(lc.LLMClient)
    c._httpx = _FakeHttpx(gap=0.001)
    c._last_error = None
    c._refresh_key = lambda: True
    c._resolve_temperature = lambda *a: 0.7
    c._record_usage = lambda *a, **k: None
    c._is_quota_error = lambda *a: False
    c._provider = {"base_url": "http://x", "default_model": "m"}
    c._api_key = "k"

    t0 = time.time()
    msg, err = c._call_chat_with_tools_stream("m", [{"role": "user", "content": "hi"}], [])
    elapsed = time.time() - t0

    assert msg is None
    assert "timeout" in err
    assert elapsed < 10, f"未在墙钟内返回，用了 {elapsed:.1f}s"
    assert c._last_error["kind"] == "timeout"


def test_stream_idle_guard():
    """块间静默过久 → 必须被空闲超时拦下。"""
    lc = _client(total=600, idle=0.5)
    c = lc.LLMClient.__new__(lc.LLMClient)
    c._httpx = _FakeHttpx(gap=2.0)   # 每块间隔 2s > idle 0.5s
    c._last_error = None
    c._refresh_key = lambda: True
    c._resolve_temperature = lambda *a: 0.7
    c._record_usage = lambda *a, **k: None
    c._is_quota_error = lambda *a: False
    c._provider = {"base_url": "http://x", "default_model": "m"}
    c._api_key = "k"

    t0 = time.time()
    msg, err = c._call_chat_with_tools_stream("m", [{"role": "user", "content": "hi"}], [])
    elapsed = time.time() - t0

    assert msg is None
    assert "idle" in err
    assert elapsed < 10, f"未及时返回，用了 {elapsed:.1f}s"


def test_turn_budget_constant_configurable():
    """整轮预算常量存在且可由环境变量覆盖。"""
    os.environ["ECO_TURN_BUDGET_S"] = "123"
    for m in [m for m in sys.modules if m.startswith("server.api.chat")]:
        del sys.modules[m]
    import server.api.chat as ch
    assert ch._TURN_BUDGET_S == 123.0
    os.environ.pop("ECO_TURN_BUDGET_S", None)
