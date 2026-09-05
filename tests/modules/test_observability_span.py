"""test_observability_span.py — 审计项 B：观测 span 接入聊天循环

覆盖：
  1) SpanTree 尊重 ECO_DIR（落盘目录可重定向，沙箱/home 只读场景）
  2) 落盘失败优雅降级（logger.warning，不抛错）
  3) _chat_with_codex_loop 产生 llm_call/tool_call span 并落盘的冒烟（mock LLM 客户端）
"""

import asyncio

import pytest

from agent_core.observability import SpanTree, set_current_tree


@pytest.fixture(autouse=True)
def _reset_current_tree():
    yield
    set_current_tree(None)


class TestEcoDirAndDegradation:
    def test_respects_eco_dir(self, tmp_path, monkeypatch):
        from agent_core.observability import _default_traces_dir

        eco = tmp_path / "eco"
        monkeypatch.setenv("ECO_DIR", str(eco))
        assert _default_traces_dir() == eco / "traces"

        tree = SpanTree(session_id="s-eco-dir")
        tree.start("round1", "llm_call", model="m")
        path = tree.save()
        assert path == eco / "traces" / "s-eco-dir.json"
        assert path.exists()

    def test_save_failure_degrades_gracefully(self, tmp_path, monkeypatch, caplog):
        import agent_core.observability as obs

        # 让 traces 目录的父路径是一个普通文件 → mkdir 失败 → save 必须返回 None 且不抛错
        blocker = tmp_path / "blocked"
        blocker.write_text("not a dir")
        monkeypatch.setattr(obs, "_default_traces_dir", lambda: blocker / "traces")

        tree = SpanTree(session_id="s-fail")
        tree.start("round1", "llm_call", model="m")
        with caplog.at_level("WARNING", logger="eco.observability"):
            path = tree.save()
        assert path is None
        assert "落盘失败" in caplog.text


class TestChatLoopSpans:
    def test_chat_loop_produces_spans(self, tmp_path, monkeypatch):
        import server.api.chat as chat_mod

        monkeypatch.setenv("ECO_DIR", str(tmp_path / "eco"))

        class FakeClient:
            _provider = {"default_model": "test-model"}
            _provider_name = "test-provider"

            def __init__(self):
                self.rounds = iter(
                    [
                        {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {"name": "statute_lookup", "arguments": '{"article": "1054"}'},
                                }
                            ],
                        },
                        {"role": "assistant", "content": "根据法典第1054条……"},
                    ]
                )

            def _call_chat_with_tools(self, model, messages, tools):
                try:
                    return next(self.rounds), None
                except StopIteration:
                    return {"role": "assistant", "content": "最终回答"}, None

        class FakeAudit:
            def record_llm_call(self, *a, **k):
                return {}

            def record_tool_call(self, *a, **k):
                return {}

        # 避免真实 TraceAudit 写 repo 内 memory-tree/data/audit
        monkeypatch.setattr(chat_mod, "_svc", lambda name, fallback: FakeAudit() if name == "trace_audit" else fallback())

        async def fake_run_tool(name, args, web_client=False):
            return "条文原文（mock）"

        monkeypatch.setattr(chat_mod, "_run_tool", fake_run_tool)

        reply, trace, _usage, _fllm, _ftok = asyncio.run(
            chat_mod._chat_with_codex_loop(
                FakeClient(), [{"role": "user", "content": "查1054条"}], "test-model", session_id="s1"
            )
        )

        # mock 客户端不回声条号，断言其本意：循环产出回复与 span 树
        assert reply and isinstance(reply, str)

        traces_dir = tmp_path / "eco" / "traces"
        tree_file = traces_dir / "web-s1.json"
        assert tree_file.exists()

        tree = SpanTree.load("web-s1", directory=traces_dir)
        kinds = [s["kind"] for s in tree.spans]
        assert kinds.count("llm_call") >= 2  # 工具轮 + 最终回答轮
        assert "tool_call" in kinds

        llm_spans = [s for s in tree.spans if s["kind"] == "llm_call"]
        assert all(s["attrs"].get("model") == "test-model" for s in llm_spans)
        assert all(s["attrs"].get("provider") == "test-provider" for s in llm_spans)

        tool_span = next(s for s in tree.spans if s["kind"] == "tool_call")
        assert tool_span["name"] == "statute_lookup"
        assert tool_span["duration_ms"] is not None
        # 全部 span 均应正常结束（有耗时字段）
        for s in tree.spans:
            assert s["duration_ms"] is not None
