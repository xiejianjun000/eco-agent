"""RuntimeExecutor 测试——L2 子任务接真实工具运行时（L1 ReAct++ 桥接）

方案 A：默认占位，ECO_RUNTIME_EXECUTOR=1 或显式传参才启用真实 executor。
离线约束：无 API key 时必须降级占位，全套测试不耗配额。
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from agent_core.commander_v2 import CommanderV2, Task
from agent_core.task_executor import RuntimeExecutor


class _FakeLLM:
    def __init__(self, usable=True):
        self._usable = usable

    def available(self):
        return self._usable

    def complete(self, prompt, system="", max_tokens=512, timeout=90.0):
        return "达标"


class _FakeLoop:
    """模拟 ReActPlusPlus：记录工具注册与 prompt，返回固定结果"""
    instances = []

    def __init__(self):
        self._tools = {}
        self._max_steps = 20
        _FakeLoop.instances.append(self)

    def register_tool(self, name, handler, description="", schema=None):
        self._tools[name] = handler

    def execute(self, task, context=None, observer=None):
        self.last_task = task
        return {"final_observation": f"真实产出: {task[:30]}", "steps": 2}


class TestDegradation:
    """LLM 缺席 → 静默降级占位（离线安全红线）"""

    def test_llm_absent_returns_placeholder(self, monkeypatch):
        import agent_core.llm_client as llm_mod
        monkeypatch.setattr(llm_mod, "get_default_client", lambda: _FakeLLM(usable=False))
        ex = RuntimeExecutor()
        out = ex(Task(description="分析需求：测试"))
        assert "完成" in out, f"降级时应返回占位产出，实际: {out}"
        assert ex.llm_loops == 0, "降级路径不得计入 LLM 循环"

    def test_no_client_at_all(self, monkeypatch):
        import agent_core.llm_client as llm_mod
        monkeypatch.setattr(llm_mod, "get_default_client", lambda: None)
        ex = RuntimeExecutor()
        out = ex(Task(description="收集资料：测试"))
        assert isinstance(out, str) and out


class TestRealLoop:
    """LLM 可用 → 起 ReAct++ 循环，工具注入，expectation/上游入 prompt"""

    def setup_method(self):
        _FakeLoop.instances.clear()

    def test_react_loop_driven_with_context(self, monkeypatch):
        import agent_core.llm_client as llm_mod
        monkeypatch.setattr(llm_mod, "get_default_client", lambda: _FakeLLM())
        import agent_core.react_loop as react_mod
        monkeypatch.setattr(react_mod, "ReActPlusPlus", _FakeLoop)

        ex = RuntimeExecutor(max_steps=5)
        task = Task(description="撰写报告：法规综述",
                    expectation="报告结构完整，结论与证据对应",
                    input={"upstream": {"收集资料": "资料A/B/C"}})
        out = ex(task)

        assert "真实产出" in out
        loop = _FakeLoop.instances[0]
        assert loop._max_steps == 5, "L2 子任务 max_steps 必须压到 5"
        assert "报告结构完整" in loop.last_task, "expectation 必须进 prompt"
        assert "资料A/B/C" in loop.last_task, "上游产出必须进 prompt"
        assert ex.llm_loops == 1

    def test_tools_registered_as_sync_handlers(self, monkeypatch):
        import agent_core.llm_client as llm_mod
        monkeypatch.setattr(llm_mod, "get_default_client", lambda: _FakeLLM())
        import agent_core.react_loop as react_mod
        monkeypatch.setattr(react_mod, "ReActPlusPlus", _FakeLoop)

        ex = RuntimeExecutor()
        ex(Task(description="执行主体：调工具"))
        loop = _FakeLoop.instances[0]
        assert len(loop._tools) > 0, "tools_registry 工具必须注入 ReAct 循环"
        for name, h in loop._tools.items():
            assert callable(h), f"工具 {name} 的 handler 必须可同步调用"

    def test_empty_final_raises_for_replan(self, monkeypatch):
        """ReAct 循环无产出 → 抛异常走 L2 replan 路径（统一失败语义）"""
        import agent_core.llm_client as llm_mod
        monkeypatch.setattr(llm_mod, "get_default_client", lambda: _FakeLLM())
        import agent_core.react_loop as react_mod

        class _EmptyLoop(_FakeLoop):
            def execute(self, task, context=None, observer=None):
                return {"final_observation": "", "steps": 1}
        monkeypatch.setattr(react_mod, "ReActPlusPlus", _EmptyLoop)

        ex = RuntimeExecutor()
        try:
            ex(Task(description="验证结果：空产出"))
            assert False, "空产出必须抛异常"
        except RuntimeError as e:
            assert "无产出" in str(e)


class TestCommanderIntegration:
    """commander_v2 侧：上游注入 + 开关 + 指标"""

    def test_upstream_output_injected_into_task_input(self):
        """波浪调度必须把上游产出注入下游 task.input（镜像 role_swarm 前置产出）"""
        seen_inputs = []

        def executor(task):
            seen_inputs.append(dict(task.input))
            return f"产出@{task.description[:12]}"

        cmd = CommanderV2(executor=executor)
        result = cmd.execute("通用上下文注入测试")
        assert result["failed"] == 0
        # 第 2 个及之后的任务必须收到上游产出
        assert len(seen_inputs) >= 2
        later = [i for i in seen_inputs if i.get("upstream")]
        assert later, "没有任何任务收到 upstream 注入"
        assert any("产出@" in str(v) for i in later for v in i["upstream"].values())

    def test_default_is_placeholder_without_env(self, monkeypatch):
        """方案 A：无环境变量时默认保持占位，不触碰 LLM"""
        monkeypatch.delenv("ECO_RUNTIME_EXECUTOR", raising=False)
        cmd = CommanderV2()
        assert type(cmd._executor).__name__ != "RuntimeExecutor"

    def test_env_enables_runtime_executor(self, monkeypatch):
        monkeypatch.setenv("ECO_RUNTIME_EXECUTOR", "1")
        cmd = CommanderV2()
        assert isinstance(cmd._executor, RuntimeExecutor)

    def test_summary_carries_llm_loops_metric(self):
        cmd = CommanderV2()
        result = cmd.execute("通用指标测试")
        assert "llm_loops" in result
        assert result["llm_loops"] == 0, "占位路径 llm_loops 必须为 0"
