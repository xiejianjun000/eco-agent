"""腾讯文档 HTML 一键上云管线测试：真实 aipage_pack.js + mock MCP 会话/PUT。

覆盖：打包产物字段、完整四步管线 happy path、pre_import 缺字段报错、
token 缺失报错、async_import 直接返回 file_url 短路、轮询进度 100 结束。
"""

import asyncio
import json
import pathlib

import pytest

from agent_core import tdocs_import as ti


def _sample_html(tmp_path: pathlib.Path) -> pathlib.Path:
    p = tmp_path / "report.html"
    p.write_text(
        "<html><head><meta charset='utf-8'></head><body><h1>冷江空气质量分析</h1><p>demo</p></body></html>", encoding="utf-8"
    )
    return p


class _FakeSession:
    def __init__(self, calls: list[tuple[str, dict]]):
        self.calls = calls
        self.ready = False

    async def initialize(self):
        self.ready = True

    async def call_tool(self, name, arguments=None):
        self.calls.append((name, arguments))
        if name == "manage.pre_import":
            return _ToolResult(
                json.dumps({"upload_url": "https://cos.example.com/up/abc", "file_key": "key-abc", "task_id": "task-1"})
            )
        if name == "manage.async_import":
            return _ToolResult(json.dumps({"task_id": "task-1", "progress": 0}))
        if name == "manage.import_progress":
            # 第一次 50，第二次 100
            progress = 100 if len([c for c in self.calls if c[0] == "manage.import_progress"]) >= 2 else 50
            return _ToolResult(
                json.dumps(
                    {
                        "task_id": "task-1",
                        "progress": progress,
                        "file_id": "file-123" if progress == 100 else "",
                        "file_url": "https://docs.qq.com/doc/xyz" if progress == 100 else "",
                    }
                )
            )
        raise AssertionError(f"unexpected tool: {name}")


class _ToolResult:
    def __init__(self, text: str):
        self.content = [_Text(text)]


class _Text:
    type = "text"

    def __init__(self, text: str):
        self.text = text


class _Ctx:
    """mock _mcp_session 上下文管理器"""

    def __init__(self, token, ClientSession, factory):
        self._session = None

    def __init_impl(self):
        pass

    async def __aenter__(self):
        calls: list[tuple[str, dict]] = []
        self.session = _FakeSession(calls)
        self.calls = calls
        return self.session

    async def __aexit__(self, *exc):
        return False


@pytest.fixture()
def fake_ctx(monkeypatch):
    class _CtxFactory:
        def __init__(self, token, ClientSession, client_factory):
            pass

        async def __aenter__(self):
            calls: list[tuple[str, dict]] = []
            self.session = _FakeSession(calls)
            self.calls = calls
            return self.session

        async def __aexit__(self, *exc):
            return False

    factory = _CtxFactory
    monkeypatch.setattr(ti, "_mcp_session", lambda token: _CtxFactory(None, None, None))
    monkeypatch.setenv(ti.TENCENT_TOKEN_ENV, "test-token")
    return factory


class _FakeResponse:
    def __init__(self, status_code=200, text=""):
        self.status_code = status_code
        self.text = text


class _FakeHttp:
    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def put(self, url, content=None, headers=None):
        return _FakeResponse(200)


# ═══════════════════════════════════
# 打包
# ═══════════════════════════════════


def test_run_pack_real(tmp_path):
    """真实 node aipage_pack.js 打包：产物 .aipage 存在且 md5/size 一致。"""
    html = _sample_html(tmp_path)
    packed = ti._run_pack(str(html), title="冷江分析")
    assert packed["size"] > 0
    assert len(packed["md5"]) == 32
    assert pathlib.Path(packed["path"]).is_file()
    assert packed["path"].endswith(".aipage")


def test_run_pack_missing_html(tmp_path):
    with pytest.raises(FileNotFoundError):
        ti._run_pack(str(tmp_path / "nope.html"))


# ═══════════════════════════════════
# 管线（mock 会话 + mock PUT）
# ═══════════════════════════════════


def test_pipeline_happy_path(tmp_path, fake_ctx, monkeypatch):
    monkeypatch.setattr(ti.httpx, "AsyncClient", _FakeHttp)
    html = _sample_html(tmp_path)
    result = asyncio.run(ti._run_pipeline(str(html), "冷江分析"))
    assert result["ok"] is True
    assert result["file_id"] == "file-123"
    assert result["file_url"] == "https://docs.qq.com/doc/xyz"
    # 四步调用顺序：pre_import → async_import → progress ≥2 次
    assert result["progress"] == 100


def test_pipeline_pre_import_missing_fields(tmp_path, fake_ctx, monkeypatch):
    monkeypatch.setattr(ti.httpx, "AsyncClient", _FakeHttp)

    class _BadSession(_FakeSession):
        async def call_tool(self, name, arguments=None):
            if name == "manage.pre_import":
                return _ToolResult(json.dumps({"error": "x"}))
            raise AssertionError

    class _BadFactory:
        async def __aenter__(self):
            return _BadSession([])

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(ti, "_mcp_session", lambda token: _BadFactory())
    with pytest.raises(RuntimeError, match="缺字段"):
        asyncio.run(ti._run_pipeline(str(_sample_html(tmp_path)), ""))


def test_pipeline_missing_token(tmp_path, monkeypatch):
    monkeypatch.delenv(ti.TENCENT_TOKEN_ENV, raising=False)
    with pytest.raises(RuntimeError, match="token"):
        asyncio.run(ti._run_pipeline(str(_sample_html(tmp_path)), ""))


def test_pipeline_async_import_direct_url(tmp_path, fake_ctx, monkeypatch):
    """async_import 直接返回 file_url 时应短路，不必等 progress=100。"""
    monkeypatch.setattr(ti.httpx, "AsyncClient", _FakeHttp)

    class _DirectSession(_FakeSession):
        async def call_tool(self, name, arguments=None):
            if name == "manage.pre_import":
                return _ToolResult(
                    json.dumps({"upload_url": "https://cos.example.com/up/abc", "file_key": "key-abc", "task_id": "task-1"})
                )
            if name == "manage.async_import":
                return _ToolResult(
                    json.dumps({"task_id": "task-1", "file_id": "file-9", "file_url": "https://docs.qq.com/doc/direct"})
                )
            raise AssertionError

    class _DirectFactory:
        async def __aenter__(self):
            return _DirectSession([])

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(ti, "_mcp_session", lambda token: _DirectFactory())
    result = asyncio.run(ti._run_pipeline(str(_sample_html(tmp_path)), ""))
    assert result["ok"] is True and result["file_url"] == "https://docs.qq.com/doc/direct"


def test_pipeline_transient_progress_error(tmp_path, fake_ctx, monkeypatch):
    """import_progress 首轮瞬时报错（11607 docID 注册延迟）应容忍并轮询到 100。"""
    monkeypatch.setattr(ti.httpx, "AsyncClient", _FakeHttp)
    calls = {"n": 0}

    class _FlakySession(_FakeSession):
        async def call_tool(self, name, arguments=None):
            if name == "manage.pre_import":
                return _ToolResult(
                    json.dumps({"upload_url": "https://cos.example.com/up/abc", "file_key": "key-abc", "task_id": "task-1"})
                )
            if name == "manage.async_import":
                return _ToolResult(json.dumps({"task_id": "task-1", "progress": 0}))
            if name == "manage.import_progress":
                calls["n"] += 1
                if calls["n"] == 1:
                    raise RuntimeError("tool execution failed: 11607:docID not match pattern")
                return _ToolResult(
                    json.dumps(
                        {"task_id": "task-1", "progress": 100, "file_id": "file-123", "file_url": "https://docs.qq.com/doc/xyz"}
                    )
                )
            raise AssertionError

    class _FlakyFactory:
        async def __aenter__(self):
            return _FlakySession([])

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(ti, "_mcp_session", lambda token: _FlakyFactory())
    result = asyncio.run(ti._run_pipeline(str(_sample_html(tmp_path)), ""))
    assert result["ok"] is True and result["progress"] == 100
    assert result["file_url"] == "https://docs.qq.com/doc/xyz"


def test_upload_http_error(tmp_path, fake_ctx, monkeypatch):
    class _FailHttp(_FakeHttp):
        async def put(self, url, content=None, headers=None):
            return _FakeResponse(403, "denied")

    monkeypatch.setattr(ti.httpx, "AsyncClient", _FailHttp)
    with pytest.raises(RuntimeError, match="PUT 上传失败"):
        asyncio.run(ti._run_pipeline(str(_sample_html(tmp_path)), ""))
