# -*- coding: utf-8 -*-
"""DAG 接 chat 主路径测试：复杂任务生成 todos、步骤完成勾选更新、-v 展示 DAG 边"""
import pytest

from agent_core.workspace import WorkspaceManager
from eco.commands import cmd_chat


@pytest.fixture()
def ws(tmp_path, monkeypatch):
    mgr = WorkspaceManager(tmp_path)
    monkeypatch.setattr("agent_core.workspace._manager", mgr)
    w = mgr.create("合力砖厂检查", category="执法检查")
    mgr.open(w.meta["slug"])
    yield w
    monkeypatch.setattr("agent_core.workspace._manager", None)


class FakeSwarm:
    """模拟 RoleSwarm：按真实 stage 标签触发 on_stage 回调"""

    def run(self, task, context="", on_stage=None):
        def s(stage, detail="", elapsed=0.0):
            if on_stage:
                on_stage(stage, detail, elapsed)
        s("任务分解", "巡查Agent ∥ 法规Agent 并行 → 文书Agent → 总管合成")
        s("巡查Agent 完成", "现场要点", 1.0)
        s("法规Agent 完成", "法条核验", 1.0)
        s("文书Agent 完成", "记录框架", 1.0)
        s("总管合成完成", "最终答复", 1.0)
        return {"contributions": {"patrol": "P", "law": "L", "doc": "D"},
                "synthesis": "最终检查清单"}

    def format_result(self, result):
        return result["synthesis"]


@pytest.fixture()
def fake_swarm(monkeypatch):
    monkeypatch.setattr("agent_core.role_swarm.get_role_swarm", lambda: FakeSwarm())


COMPLEX_Q = "对合力砖厂开展全面检查，出具检查清单和现场检查记录"


def test_complex_task_generates_and_completes_todos(ws, fake_swarm, capsys):
    from agent_core.role_swarm import is_complex_task
    assert is_complex_task(COMPLEX_Q)
    answer = cmd_chat._maybe_swarm(COMPLEX_Q)
    assert answer == "最终检查清单"
    todos = ws.todos()
    # 任务分解已写入 todos
    assert "[dag:patrol]" in todos and "[dag:law]" in todos
    assert "[dag:doc]" in todos and "[dag:synthesis]" in todos
    # 全部步骤执行完成 → 勾选
    for sid in ("patrol", "law", "doc", "synthesis"):
        assert f"- [x] [dag:{sid}]" in todos
    assert "- [ ]" not in todos  # 无遗留未勾选项


def test_dag_edges_shown_in_verbose(ws, fake_swarm):
    from eco.trace import get_tracer, set_verbose
    set_verbose(True)
    try:
        cmd_chat._maybe_swarm(COMPLEX_Q, tracer=get_tracer())
    finally:
        set_verbose(False)
    phases = [e["content"] for e in get_tracer().events if e.get("phase") == "dag"]
    assert phases, "verbose 模式应展示 DAG 边"
    dag_line = phases[0]
    assert "patrol -> doc" in dag_line and "law -> doc" in dag_line
    assert "doc -> synthesis" in dag_line


def test_simple_task_no_dag(ws, fake_swarm):
    assert cmd_chat._maybe_swarm("什么是双随机一公开？") is None
    assert "[dag:" not in ws.todos()


def test_partial_failure_keeps_unchecked(ws, monkeypatch):
    """某 DAG 步骤失败：对应 todo 不勾选，保留未完成状态"""
    class FailSwarm(FakeSwarm):
        def run(self, task, context="", on_stage=None):
            if on_stage:
                on_stage("巡查Agent 完成", "", 0.5)
                on_stage("法规Agent 完成", "", 0.5)
                on_stage("总管合成完成", "", 0.5)
            return {"contributions": {"patrol": "P", "law": "L", "doc": ""},
                    "synthesis": "部分结果"}

    monkeypatch.setattr("agent_core.role_swarm.get_role_swarm", lambda: FailSwarm())
    cmd_chat._maybe_swarm(COMPLEX_Q)
    todos = ws.todos()
    assert "- [x] [dag:patrol]" in todos
    assert "- [ ] [dag:doc]" in todos  # 文书步骤失败 → 未勾选
