"""span 树可观测性测试：父子嵌套/耗时字段/落盘/树形渲染/OTLP 导出 + chat_with_tools 集成"""

import json

from agent_core.observability import SpanTree


class TestSpanTreeBasic:
    def test_nested_spans_parent_child_and_duration(self, tmp_path, monkeypatch):
        monkeypatch.setattr("agent_core.observability.TRACES_DIR", tmp_path)
        tree = SpanTree(meta={"model": "m"})
        root = tree.start("chat", "session")
        llm = tree.start("round1", "llm_call", model="deepseek-chat")
        tool = tree.start("save_document", "tool_call", args={"filename": "a.md"})
        tree.end(tool, result="ok")
        tree.end(llm, finish_reason="tool_calls", prompt_tokens=10, completion_tokens=5)
        tree.end(root)

        spans = {s["span_id"]: s for s in tree.spans}
        assert spans[tool]["parent_id"] == llm
        assert spans[llm]["parent_id"] == root
        assert spans[root]["parent_id"] is None
        for s in tree.spans:
            assert s["duration_ms"] is not None and s["duration_ms"] >= 0
            assert s["start_iso"]
        assert spans[llm]["attrs"]["prompt_tokens"] == 10
        assert spans[llm]["attrs"]["finish_reason"] == "tool_calls"

        # 落盘 + 重新加载
        path = tree.save()
        assert path.name == f"{tree.session_id}.json"
        loaded = SpanTree.load(tree.session_id)
        assert len(loaded.spans) == 3
        assert tree.session_id in SpanTree.list_sessions()

    def test_render_tree_shows_hierarchy(self):
        tree = SpanTree()
        root = tree.start("chat", "session")
        llm = tree.start("round1", "llm_call", model="m")
        tree.end(llm, finish_reason="stop", prompt_tokens=3, completion_tokens=7)
        tree.end(root)
        text = tree.render_tree()
        assert "session:chat" in text
        assert "llm_call:round1" in text and "finish=stop" in text
        assert "in=3" in text and "out=7" in text
        assert "└─" in text

    def test_otlp_export_structure(self, tmp_path):
        tree = SpanTree()
        root = tree.start("chat", "session")
        llm = tree.start("round1", "llm_call", model="m")
        tool = tree.start("t", "tool_call", args={})
        tree.end(tool)
        tree.end(llm)
        tree.end(root)
        out = tree.export_otlp(tmp_path / "x.otlp.json")
        data = json.loads(out.read_text(encoding="utf-8"))
        rs = data["resourceSpans"][0]
        spans = rs["scopeSpans"][0]["spans"]
        assert len(spans) == 3
        trace_ids = {s["traceId"] for s in spans}
        assert len(trace_ids) == 1  # 同一 trace
        by_name = {s["name"]: s for s in spans}
        tool_span = by_name["tool_call:t"]
        llm_span = by_name["llm_call:round1"]
        assert tool_span["parentSpanId"] == llm_span["spanId"]
        assert "startTimeUnixNano" in tool_span and "endTimeUnixNano" in tool_span


class TestSpanTreeChatIntegration:
    """模拟一轮含工具调用的会话（mock HTTP 层），断言 span 树父子关系与耗时齐全"""

    def _client(self, monkeypatch):
        from agent_core.llm_client import LLMClient

        c = LLMClient()
        monkeypatch.setattr(c, "_api_key", "sk-test")
        monkeypatch.setattr(c, "_disabled", False)
        assert c.available()
        return c

    def test_tool_round_span_tree(self, monkeypatch, tmp_path):
        monkeypatch.setattr("agent_core.decisions.DECISIONS_FILE", tmp_path / "dec.jsonl")
        c = self._client(monkeypatch)
        rounds = iter(
            [
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "save_document", "arguments": '{"filename": "a.md", "content": "x"}'},
                        }
                    ],
                },
                {"role": "assistant", "content": "已保存。"},
            ]
        )

        def fake_call(model, messages, tools):
            c._last_usage = {"prompt_tokens": 11, "completion_tokens": 6}
            return next(rounds), None

        monkeypatch.setattr(c, "_call_chat_with_tools", fake_call)

        async def fake_exec(name, args):
            return "saved ok"

        monkeypatch.setattr("agent_core.tools_registry.execute_tool", fake_exec)

        tree = SpanTree()
        root = tree.start("chat", "session")
        answer = c.chat_with_tools([{"role": "user", "content": "保存"}], tools=[{"x": 1}], stream=False, spans=tree)
        tree.end(root)
        assert answer == "已保存。"

        kinds = [s["kind"] for s in tree.spans]
        assert kinds.count("llm_call") == 2  # 工具轮 + 最终回答轮
        assert "tool_call" in kinds
        spans = tree.spans
        tool_span = next(s for s in spans if s["kind"] == "tool_call")
        llm1 = next(s for s in spans if s["kind"] == "llm_call")
        assert tool_span["parent_id"] == llm1["span_id"]
        assert tool_span["name"] == "save_document"
        for s in spans:
            assert s["duration_ms"] is not None
        assert llm1["attrs"]["prompt_tokens"] == 11
        final_llm = [s for s in spans if s["kind"] == "llm_call"][-1]
        assert final_llm["attrs"]["finish_reason"] == "stop"
