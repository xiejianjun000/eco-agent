"""工具名规范化（P0）与 CLI 轨迹模式测试——全部 mock，不联网"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
import asyncio
import json

from agent_core import tools_registry as tr
from eco.trace import Tracer


# ── P0: 名称规范化 ────────────────────────────────────────
class TestToolNameNormalization:
    def test_all_exported_names_valid(self):
        """导出的工具名必须全部匹配 ^[a-zA-Z0-9_-]{1,64}$"""
        for n in tr.get_tool_names():
            assert tr.TOOL_NAME_RE.match(n), f"非法工具名导出: {n!r}"

    def test_all_exported_names_unique(self):
        """导出的工具名必须唯一（重名会让 LLM 端整批 400）"""
        names = tr.get_tool_names()
        assert len(names) == len(set(names))

    def test_chinese_name_slugified(self):
        """含中文的非法名映射为固定 slug"""
        assert tr.normalize_tool_name("query_snow亮的视频") == "query_snow_xueliang_video"
        assert "query_snow_xueliang_video" in tr.get_tool_names()
        assert "query_snow亮的视频" not in tr.get_tool_names()

    def test_slug_reverse_lookup(self):
        """slug ↔ 原始名映射反查"""
        assert tr.resolve_tool_name("query_snow_xueliang_video") == "query_snow亮的视频"
        assert tr.resolve_tool_name("query_air_quality") == "query_air_quality"

    def test_renamed_report(self):
        renamed = tr.get_renamed_tools()
        assert renamed.get("query_snow亮的视频") == "query_snow_xueliang_video"

    def test_duplicate_dedup_report(self):
        dups = tr.get_duplicate_tools()
        assert "query_air_quality" in dups

    def test_generic_invalid_name_fallback(self):
        """未知非法名走通用 slug 化，结果合法"""
        slug = tr.normalize_tool_name("查.询/天气（北京）")
        assert tr.TOOL_NAME_RE.match(slug)

    def test_decorator_registers_both_names(self):
        @tr.tool("测试.工具")
        def _dummy(x: str = ""):
            return {"x": x}
        slug = tr.resolve_tool_name("测试.工具")
        out = asyncio.run(tr.execute_tool(slug, {"x": "1"}))
        assert json.loads(out) == {"x": "1"}

    def test_execute_tool_via_slug_and_original(self):
        """execute_tool 同时接受 slug 与原始名"""
        r1 = json.loads(asyncio.run(tr.execute_tool(
            "calculate_carbon_emission", {"industry": "钢铁", "energy_consumption": "10"})))
        assert r1["emission_t"] == 18.0
        r2 = json.loads(asyncio.run(tr.execute_tool(
            tr.resolve_tool_name("calculate_carbon_emission"),
            {"industry": "钢铁", "energy_consumption": "10"})))
        assert r2 == r1


# ── 轨迹模式 ─────────────────────────────────────────────
class _FakeMsg:
    def __init__(self, content=None, tool_calls=None):
        self._d = {"content": content}
        if tool_calls:
            self._d["tool_calls"] = tool_calls

    def get(self, k, default=None):
        return self._d.get(k, default)


class TestTracer:
    def test_disabled_tracer_no_output(self, capsys):
        t = Tracer(enabled=False, audit=False)
        t.round_start(1)
        t.thought("思考")
        t.tool_call("query_air_quality", {"city": "娄底"})
        assert capsys.readouterr().out == ""
        assert t.events != []  # 禁用时不输出，但仍记录事件供审计

    def test_enabled_tracer_outputs_symbols(self, capsys):
        t = Tracer(enabled=True, audit=False, console=None)
        t.round_start(1)
        t.thought("先查空气质量再回答")
        t.tool_call("query_air_quality", {"city": "娄底"})
        t.tool_result("query_air_quality", '{"aqi": 14, "level": "优"}', 0.3)
        t.finish()
        out = capsys.readouterr().out
        assert "[轮次 1]" in out
        assert "💭" in out and "🔧" in out and "👁" in out
        assert "query_air_quality" in out

    def test_truncation(self):
        from eco.trace import _truncate
        long_text = "x" * 200
        assert len(_truncate(long_text, 80)) <= 80

    def test_audit_chain_source_trace(self, tmp_path):
        from agent_core.prompt_engine import PromptAuditChain
        chain = PromptAuditChain(path=tmp_path / "audit.jsonl")
        t = Tracer(enabled=False, audit=True)
        t._audit_chain = chain
        t.tool_call("query_air_quality", {"city": "娄底"})
        lines = (tmp_path / "audit.jsonl").read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["source"] == "trace"
        assert chain.verify_chain()["valid"]

    def test_swarm_stage_and_retrieval(self, capsys):
        t = Tracer(enabled=True, audit=False, console=None)
        t.swarm_stage("任务分解", "patrol ∥ law → doc → synthesis")
        t.retrieval(3, "bm25")
        t.retrieval(0)
        out = capsys.readouterr().out
        assert "任务分解" in out
        assert "命中 3 个历史片段" in out
        assert "未命中" in out


class TestChatWithToolsTrace:
    def test_tracer_receives_loop_events(self, monkeypatch):
        """mock LLM：第一轮 tool_calls，第二轮文本 → tracer 收到完整轨迹"""
        from agent_core.llm_client import LLMClient

        tc = [{"id": "c1", "type": "function",
               "function": {"name": "calculate_carbon_emission",
                            "arguments": '{"industry": "钢铁", "energy_consumption": "10"}'}}]
        responses = [
            {"choices": [{"message": {"content": "先算碳排放", "tool_calls": tc}}]},
            {"choices": [{"message": {"content": "排放 18 吨"}}]},
        ]
        calls = {"i": 0}

        class FakeResp:
            status_code = 200
            text = ""

            def json(self):
                r = responses[min(calls["i"], len(responses) - 1)]
                calls["i"] += 1
                return r

        monkeypatch.setenv("ECO_LLM_DISABLE", "")
        monkeypatch.setenv("ECO_PROVIDER", "kimi")
        monkeypatch.setenv("KIMI_API_KEY", "sk-test")
        client = LLMClient()
        monkeypatch.setattr(client._httpx, "post", lambda *a, **k: FakeResp())

        tracer = Tracer(enabled=True, audit=False, console=None)
        out = client.chat_with_tools([{"role": "user", "content": "q"}],
                                     tools=[], tracer=tracer)
        assert "18" in out
        phases = [e["phase"] for e in tracer.events]
        assert "round" in phases
        assert "thought" in phases
        assert "tool_call" in phases
        assert "tool_result" in phases
        assert "finish" in phases

    def test_no_tracer_backward_compatible(self, monkeypatch):
        """不传 tracer 时行为不变"""
        from agent_core.llm_client import LLMClient

        class FakeResp:
            status_code = 200
            text = ""

            def json(self):
                return {"choices": [{"message": {"content": "ok"}}]}

        monkeypatch.setenv("ECO_LLM_DISABLE", "")
        monkeypatch.setenv("ECO_PROVIDER", "kimi")
        monkeypatch.setenv("KIMI_API_KEY", "sk-test")
        client = LLMClient()
        monkeypatch.setattr(client._httpx, "post", lambda *a, **k: FakeResp())
        assert client.chat_with_tools([{"role": "user", "content": "q"}], tools=[]) == "ok"


class TestSwarmStageHook:
    def test_on_stage_called(self):
        from agent_core.role_swarm import RoleSwarm

        class MockClient:
            def complete(self, prompt, system="", max_tokens=500):
                return f"产出:{prompt[:10]}"

        stages = []
        swarm = RoleSwarm(client=MockClient())
        result = swarm.run("测试任务", on_stage=lambda s, d="", e=0.0: stages.append(s))
        assert any("任务分解" in s for s in stages)
        assert any("合成" in s for s in stages)
        assert result["synthesis"]
