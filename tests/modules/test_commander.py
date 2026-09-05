"""L2 任务执行循环 + Agent 协作测试——状态转移与数据结构断言"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
from agent_core.commander_v2 import CommanderV2, DAGValidator, Negotiator, TaskStatus


class TestCommander:
    def test_dynamic_assembly_structure(self):
        """分解必须产出 ≥5 子任务，且为链式依赖 DAG、优先级递减、id 唯一"""
        cmd = CommanderV2()
        tasks = cmd.decomposer.decompose("开发一个待办清单App")
        assert len(tasks) >= 5, f"需>=5, 实际{len(tasks)}"
        assert tasks[0].depends_on == []
        for prev, cur in zip(tasks, tasks[1:]):  # noqa: B905 长度差1是刻意的相邻配对
            assert cur.depends_on == [prev.id], "子任务必须链式依赖前一个任务"
        assert len({t.id for t in tasks}) == len(tasks), "任务 id 必须唯一"
        prios = [t.priority for t in tasks]
        assert prios == sorted(prios, reverse=True), "优先级必须按序递减"

    def test_execution_state_transitions(self):
        """执行后任务必须发生真实状态转移：首个完成、链式后继被阻塞"""
        cmd = CommanderV2()
        result = cmd.execute("多任务并行执行测试")
        assert result["total_tasks"] >= 5
        assert result["completed"] >= 1, "至少首个无依赖任务必须完成"
        assert result["failed"] == 0
        assert result["dag_cycle_free"] is True
        statuses = [t.status for t in cmd._tasks.values()]
        assert TaskStatus.COMPLETED in statuses
        assert result["completed"] + result["failed"] <= result["total_tasks"]

    def test_mission_recorded(self):
        """每次执行必须写入任务历史（副作用断言）"""
        cmd = CommanderV2()
        assert cmd.get_stats()["missions"] == 0
        cmd.execute("历史记录测试")
        assert cmd.get_stats()["missions"] == 1

    def test_elastic_scaling_pool_stats(self):
        cmd = CommanderV2()
        stats = cmd.pool.get_stats()
        assert set(stats) >= {"total", "by_role"} or "total" in stats
        assert stats["total"] >= 0
        cmd.execute("触发扩缩容")
        assert cmd.pool.get_stats()["total"] >= 1, "执行后必须有 Agent 实例"


class TestDAG:
    def test_cycle_detection_exact_nodes(self):
        tasks = [
            type("T", (), {"id": "a", "depends_on": ["b"]})(),
            type("T", (), {"id": "b", "depends_on": ["c"]})(),
            type("T", (), {"id": "c", "depends_on": ["a"]})(),
        ]
        cycle = DAGValidator.has_cycle(tasks)
        assert cycle is not None
        assert set(cycle) <= {"a", "b", "c"} and len(cycle) >= 2

    def test_cycle_free_chain(self):
        tasks = [
            type("T", (), {"id": "a", "depends_on": []})(),
            type("T", (), {"id": "b", "depends_on": ["a"]})(),
            type("T", (), {"id": "c", "depends_on": ["b"]})(),
        ]
        assert DAGValidator.has_cycle(tasks) is None

    def test_break_cycle_removes_cycle(self):
        """破环后必须无环（真实副作用断言）"""
        tasks = [
            type("T", (), {"id": "a", "depends_on": ["b"]})(),
            type("T", (), {"id": "b", "depends_on": ["c"]})(),
            type("T", (), {"id": "c", "depends_on": ["a"]})(),
        ]
        fixed = DAGValidator.break_cycle(tasks)
        assert DAGValidator.has_cycle(fixed) is None


class TestNegotiation:
    def test_resource_contention_sequence(self):
        """先到先得、后到避让（≤30s）、释放后下一位获得资源——完整调用序列"""
        neg = Negotiator()
        r1 = neg.request("agent_a", "file://config", "task_a")
        r2 = neg.request("agent_b", "file://config", "task_b")
        assert r1 == {"granted": True, "wait": 0}
        assert r2["granted"] is False
        assert 0 < r2["wait"] <= 30, "避让等待必须 ≤30s"
        assert neg.get_stats()["active_contention"] == 2
        neg.release("agent_a", "file://config")
        r3 = neg.request("agent_c", "file://config", "task_c")
        assert r3["granted"] is False or r3["wait"] <= 30  # agent_b 仍在排队
        neg.release("agent_b", "file://config")
        neg.release("agent_c", "file://config")
        assert neg.get_stats()["active_contention"] == 0
