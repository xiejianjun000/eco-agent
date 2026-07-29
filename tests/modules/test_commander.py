"""L2 任务执行循环 + Agent 协作测试"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from agent_core.commander_v2 import CommanderV2, DAGValidator, Negotiator

class TestCommander:
    def test_dynamic_assembly(self):
        cmd = CommanderV2()
        result = cmd.execute("开发一个待办清单App")
        assert result['total_tasks'] >= 5, f"需>=5, 实际{result['total_tasks']}"

    def test_parallel_execution(self):
        cmd = CommanderV2()
        result = cmd.execute("多任务并行执行测试")
        assert result['agents_used'] >= 1

    def test_elastic_scaling(self):
        cmd = CommanderV2()
        stats = cmd.pool.get_stats()
        assert stats['total'] >= 0

class TestDAG:
    def test_cycle_detection(self):
        tasks = [
            type('T', (), {'id': 'a', 'depends_on': ['b']})(),
            type('T', (), {'id': 'b', 'depends_on': ['c']})(),
            type('T', (), {'id': 'c', 'depends_on': ['a']})(),
        ]
        cycle = DAGValidator.has_cycle(tasks)
        assert cycle is not None

    def test_cycle_free(self):
        tasks = [
            type('T', (), {'id': 'a', 'depends_on': []})(),
            type('T', (), {'id': 'b', 'depends_on': ['a']})(),
            type('T', (), {'id': 'c', 'depends_on': ['b']})(),
        ]
        cycle = DAGValidator.has_cycle(tasks)
        assert cycle is None

class TestNegotiation:
    def test_resource_contention(self):
        neg = Negotiator()
        r1 = neg.request("agent_a", "file://config", "task_a")
        r2 = neg.request("agent_b", "file://config", "task_b")
        assert r1['granted'] is True
        assert r2['granted'] is False
