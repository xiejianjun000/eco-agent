"""L1 ReAct++ LLM 路径缺陷修复测试（冒烟实测暴露的三缺陷）

  缺陷1：工具参数硬编码 {"query": ...} → schema 进 prompt + LLM 结构化 action
  缺陷2：完成时拿 thought（计划）充产出 → 显式交付合成步骤
  缺陷3：全量工具灌给所有角色 → task_executor 角色感知工具过滤

离线红线：无 LLM 时规则路径行为与修复前完全一致（既有测试契约不变）。
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from agent_core.react_loop import ReActPlusPlus
from agent_core.commander_v2 import AgentRole, Task
from agent_core.task_executor import RuntimeExecutor


class _DispatchFakeLLM:
    """按 prompt 内容分发的 fake LLM：think/confidence/decide/synthesize 各给各的回答"""
    def __init__(self, decide_reply='{"action": "complete"}', synth_reply="综合交付物"):
        self.decide_reply = decide_reply
        self.synth_reply = synth_reply
        self.prompts = []

    def available(self):
        return True

    def complete(self, prompt, system="", max_tokens=512, timeout=90.0):
        self.prompts.append(prompt)
        if "置信度" in prompt:
            return "0.9"
        if "JSON" in prompt and "action" in prompt:
            return self.decide_reply
        if "最终交付" in prompt:
            return self.synth_reply
        return "下一步思考"


def _patch_llm(monkeypatch, fake):
    # react_loop 在模块顶层 from ... import get_default_client，
    # 名字已绑定进自己命名空间——必须 patch react_loop 模块内的引用
    import agent_core.react_loop as react_mod
    monkeypatch.setattr(react_mod, "get_default_client", lambda: fake)


class TestStructuredAction:
    """缺陷1：LLM 按真实 schema 产出结构化 action，不再硬编码 query 参数"""

    def test_llm_supplied_args_reach_handler(self, monkeypatch):
        """LLM 给出的 args 必须原样到达 handler（不再是 query=任务文本）"""
        fake = _DispatchFakeLLM(
            decide_reply='{"action": "tool", "tool": "query_air_quality", "args": {"city": "北京", "date": "2026-08-01"}}')
        _patch_llm(monkeypatch, fake)

        loop = ReActPlusPlus()
        received = []
        loop.register_tool(
            "query_air_quality",
            lambda **kw: received.append(kw) or "空气质量数据",
            description="查询城市空气质量",
            schema={"type": "object", "properties": {"city": {"type": "string"}, "date": {"type": "string"}},
                    "required": ["city"]},
        )
        loop.execute("查询北京空气质量")

        assert received, "工具未被调用"
        assert received[0] == {"city": "北京", "date": "2026-08-01"}, \
            f"LLM 结构化参数必须原样到达，实际: {received[0]}"

    def test_schema_appears_in_decide_prompt(self, monkeypatch):
        """工具参数 schema 必须进入决策 prompt（LLM 不看 schema 就是瞎猜）"""
        fake = _DispatchFakeLLM()
        _patch_llm(monkeypatch, fake)

        loop = ReActPlusPlus()
        loop.register_tool("search_regulation", lambda **kw: "法规",
                           description="检索法规",
                           schema={"type": "object", "properties": {"keyword": {"type": "string"}}})
        loop.execute("检索法规")

        decide_prompts = [p for p in fake.prompts if "action" in p and "JSON" in p]
        assert decide_prompts, "未发生结构化决策调用"
        assert "keyword" in decide_prompts[0], f"schema 未进入决策 prompt: {decide_prompts[0][:200]}"

    def test_invalid_json_falls_back_to_rule(self, monkeypatch):
        """LLM 决策输出非法 JSON → 降级规则路径（query 约定），行为同修复前"""
        fake = _DispatchFakeLLM(decide_reply="我觉得应该调用工具但是我不会写JSON")
        _patch_llm(monkeypatch, fake)

        loop = ReActPlusPlus()
        calls = []
        loop.register_tool("search", lambda query: calls.append(query) or "结果", "搜索")
        result = loop.execute("search 大气污染防治")

        assert calls == ["search 大气污染防治"], f"降级后必须走 query 约定: {calls}"
        assert result["final_observation"]


class TestExplicitDelivery:
    """缺陷2：完成必须经显式交付合成，thought（计划）不得充当产出"""

    def test_final_is_synthesized_not_thought(self, monkeypatch):
        fake = _DispatchFakeLLM(synth_reply="【交付】大气污染防治调研笔记正文")
        _patch_llm(monkeypatch, fake)

        loop = ReActPlusPlus()
        loop.register_tool("search", lambda query: "搜索结果", "搜索")
        result = loop.execute("search 并整理调研笔记")

        assert result["final_observation"] == "【交付】大气污染防治调研笔记正文", \
            f"最终产出必须来自交付合成: {result['final_observation'][:60]}"
        synth_calls = [p for p in fake.prompts if "最终交付" in p]
        assert synth_calls, "完成时未发生交付合成调用"

    def test_synthesize_failure_falls_back(self, monkeypatch):
        """交付合成返回空 → 降级旧逻辑（thought / 任务完成），不崩"""
        fake = _DispatchFakeLLM(synth_reply="")
        _patch_llm(monkeypatch, fake)

        loop = ReActPlusPlus()
        loop.register_tool("search", lambda query: "结果", "搜索")
        result = loop.execute("search 测试")
        assert result["final_observation"], "合成失败也必须有最终产出"


class _CaptureLoop:
    """捕获 register_tool 调用的 fake ReAct 循环（供角色过滤测试）"""
    instances = []

    def __init__(self):
        self._tools = {}
        self._max_steps = 20
        _CaptureLoop.instances.append(self)

    def register_tool(self, name, handler, description="", schema=None):
        self._tools[name] = {"handler": handler, "schema": schema}

    def execute(self, task, context=None, observer=None):
        return {"final_observation": "产出", "steps": 1}


class TestRoleAwareToolFilter:
    """缺陷3：分析类角色只给只读（L1）工具，执行类角色给全量"""

    def setup_method(self):
        _CaptureLoop.instances.clear()

    def _run(self, monkeypatch, role):
        import agent_core.llm_client as llm_mod
        monkeypatch.setattr(llm_mod, "get_default_client", lambda: _DispatchFakeLLM())
        import agent_core.react_loop as react_mod
        monkeypatch.setattr(react_mod, "ReActPlusPlus", _CaptureLoop)
        ex = RuntimeExecutor()
        ex(Task(description="执行任务", agent_role=role, expectation="判据"))
        return _CaptureLoop.instances[-1]

    def test_analyst_gets_readonly_tools_only(self, monkeypatch):
        loop = self._run(monkeypatch, AgentRole.ANALYST)
        assert loop._tools, "分析角色也应有只读工具"
        from agent_core.permissions import tool_risk_level
        risky = [n for n in loop._tools if tool_risk_level(n) not in ("L1",)]
        assert not risky, f"分析角色不应拿到 L2+ 工具: {risky[:5]}"

    def test_executor_role_gets_full_registry(self, monkeypatch):
        analyst_loop = self._run(monkeypatch, AgentRole.ANALYST)
        custom_loop = self._run(monkeypatch, AgentRole.CUSTOM)
        assert len(custom_loop._tools) > len(analyst_loop._tools), \
            "执行类角色工具数必须多于分析类"

    def test_schema_passed_to_loop(self, monkeypatch):
        """注册进循环的工具必须携带 tools_registry 的 parameters schema"""
        loop = self._run(monkeypatch, AgentRole.CUSTOM)
        with_schema = [n for n, t in loop._tools.items() if t["schema"]]
        assert with_schema, "没有任何工具携带 schema（LLM 无法得知参数签名）"
