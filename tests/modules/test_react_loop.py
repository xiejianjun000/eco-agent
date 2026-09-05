"""L1 ReAct++ 循环测试——真实行为断言（工具调用序列/中断注入/回滚副作用）"""

import os
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
from agent_core.react_loop import ReActPlusPlus, ReActState


class TestReActLoop:
    """L1 微观行动循环测试"""

    def test_tool_invocation_and_params(self):
        """工具必须被真实调用一次，且收到任务文本作为 query 参数"""
        loop = ReActPlusPlus()
        calls = []
        loop.register_tool("search", lambda query: calls.append(query) or "搜索结果", "搜索工具")
        result = loop.execute("search 大气污染防治法")
        assert calls == ["search 大气污染防治法"], f"工具调用参数不符: {calls}"
        assert result["steps"] >= 1
        assert result["interrupted"] is False
        assert result["final_observation"] == "任务完成"

    def test_execution_history_recorded(self):
        """每次执行必须写入历史，统计数据随之更新（副作用断言）"""
        loop = ReActPlusPlus()
        loop.register_tool("echo", lambda query: query, "测试工具")
        assert loop.get_stats()["total_executions"] == 0
        loop.execute("echo 任务甲")
        loop.execute("echo 任务乙")
        stats = loop.get_stats()
        assert stats["total_executions"] == 2
        assert stats["avg_steps"] >= 1

    def test_tool_exception_contained(self):
        """工具抛异常：不外溢、被记录进 action_result，循环正常收尾"""
        loop = ReActPlusPlus()
        boom_calls = [0]

        def boom(query):
            boom_calls[0] += 1
            raise RuntimeError("爆炸")

        loop.register_tool("boom", boom, "必炸工具")
        result = loop.execute("boom 触发异常")
        assert boom_calls[0] == 1  # 当前实现：工具异常不外溢，不触发自动重试
        assert result["retries"] == 0
        assert loop.get_stats()["total_executions"] == 1

    def test_interrupt_injection(self):
        """中断注入：运行中打断，循环必须退出且如实标记 interrupted"""
        loop = ReActPlusPlus()
        entered = threading.Event()

        def slow_tool(query):
            entered.set()
            time.sleep(1.0)
            return "慢结果"

        loop.register_tool("slow", slow_tool, "慢工具")
        outcome = {}
        t = threading.Thread(target=lambda: outcome.update(loop.execute("slow 任务")), daemon=True)
        t.start()
        assert entered.wait(timeout=2), "工具未进入，无法测试中断"
        loop.interrupt()
        t.join(timeout=5)
        assert not t.is_alive(), "中断后循环未退出"
        assert outcome["interrupted"] is True
        assert outcome["steps"] <= 2

    def test_rollback_restores_checkpoint(self):
        """原子化回滚：可变状态恢复到检查点，重试计数保留，回滚次数累加"""
        loop = ReActPlusPlus()
        state = ReActState()
        state.rollback_point = {"task": "原始任务"}
        state.observation = "被污染的观测"
        state.thought = "错误思路"
        state.action = "wrong_action"
        state.action_result = "错误结果"
        state.confidence = 0.1
        state.retry_count = 2
        loop._rollback(state)
        assert state.observation == "原始任务"
        assert state.thought == "" and state.action == "" and state.action_result == ""
        assert state.confidence == 1.0
        assert state.retry_count == 2, "回滚不得清除重试计数"
        assert state.rollback_point["rollback_count"] == 1
        loop._rollback(state)
        assert state.rollback_point["rollback_count"] == 2

    def test_confidence_gating_triggers_reflect(self):
        """置信度低于阈值必须触发 PAUSE & REFLECT（调用序列断言）"""
        loop = ReActPlusPlus()
        loop.register_tool("echo", lambda query: query, "测试工具")
        reflect_calls = []
        orig_reflect = loop._pause_reflect

        def spy_reflect(state, context):
            reflect_calls.append(state.step)
            return orig_reflect(state, context)

        loop._pause_reflect = spy_reflect
        loop._estimate_confidence = lambda thought, state: 0.1  # 强制低置信度
        loop.execute("echo 低置信任务")
        assert len(reflect_calls) >= 1, "低置信度未触发反思"
