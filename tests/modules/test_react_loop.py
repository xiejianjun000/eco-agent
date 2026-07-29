"""L1 ReAct++ 循环测试"""
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from agent_core.react_loop import ReActPlusPlus

class TestReActLoop:
    """L1 微观行动循环测试"""

    def test_basic_execution(self):
        loop = ReActPlusPlus()
        loop.register_tool("echo", lambda x: x, "测试工具")
        result = loop.execute("test echo")
        assert result['steps'] > 0
        assert result['confidence'] >= 0
        assert result['total_time_ms'] >= 0

    def test_confidence_gating(self):
        loop = ReActPlusPlus()
        loop.register_tool("echo", lambda x: x, "测试工具")
        result = loop.execute("unclear task")
        assert result['steps'] >= 1

    def test_retry_mechanism(self):
        loop = ReActPlusPlus()
        call_count = [0]
        def failing_tool(x):
            call_count[0] += 1
            if call_count[0] < 3: raise Exception("transient error")
            return "success"
        loop.register_tool("test", failing_tool, "测试")
        result = loop.execute("test retry")
        assert result['retries'] <= 3
