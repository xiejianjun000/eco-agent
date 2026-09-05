#!/usr/bin/env python3
"""role_swarm 三角色协作测试（LLM 层 mock）"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from agent_core.prompt_engine import PromptAuditChain
from agent_core.role_swarm import ROLE_ORDER, ROLES, RoleSwarm, is_complex_task


class MockClient:
    """mock LLMClient.chat：按 system 内容回显角色"""

    def __init__(self):
        self.calls = []

    def chat(self, messages, model="", stream=False, temperature=0.7):
        system = messages[0]["content"]
        user = messages[-1]["content"]
        self.calls.append({"system": system, "user": user, "model": model})
        if "总管" in system:
            text = "[合成] 最终检查清单（综合三角色）"
        elif "现场巡查专家" in system:
            text = "[巡查] 现场检查要点与取证规范"
        elif "法规核验专家" in system:
            text = "[法规] 《大气污染防治法》第二十条"
        elif "执法文书专家" in system:
            text = "[文书] 检查记录框架与巡查清单"
        else:
            text = "[mock]"
        return {"choices": [{"message": {"content": text}}]}


@pytest.fixture()
def swarm(tmp_path):
    return RoleSwarm(client=MockClient(), audit_chain=PromptAuditChain(tmp_path / "audit.jsonl"))


class TestComplexity:
    @pytest.mark.parametrize(
        "q",
        [
            "对合力砖厂做一次全套大气检查",
            "制定专项执法检查方案并生成检查清单",
            "联合检查组对园区开展全面排查并出具报告",
        ],
    )
    def test_complex(self, q):
        assert is_complex_task(q) is True

    @pytest.mark.parametrize(
        "q",
        [
            "大气法第二十条是什么",
            "未批先建怎么处罚",
            "你好",
        ],
    )
    def test_simple_not_complex(self, q):
        assert is_complex_task(q) is False


class TestSwarmRun:
    def test_dag_all_roles_contribute(self, swarm):
        r = swarm.run("对合力砖厂做一次全套大气检查")
        assert set(r["contributions"].keys()) == set(ROLE_ORDER)
        assert "[巡查]" in r["contributions"]["patrol"]
        assert "[法规]" in r["contributions"]["law"]
        assert "[文书]" in r["contributions"]["doc"]
        assert "[合成]" in r["synthesis"]
        assert r["errors"] == {}
        assert r["task_id"]

    def test_doc_depends_on_patrol_and_law(self, swarm):
        swarm.run("对合力砖厂做一次全套大气检查")
        doc_call = [c for c in swarm.client.calls if "执法文书专家" in c["system"]][0]
        assert "[巡查]" in doc_call["user"]
        assert "[法规]" in doc_call["user"]

    def test_synthesis_gets_all_contributions(self, swarm):
        swarm.run("对合力砖厂做一次全套大气检查")
        synth_call = [c for c in swarm.client.calls if "总管" in c["system"]][0]
        for marker in ("[巡查]", "[法规]", "[文书]"):
            assert marker in synth_call["user"]

    def test_audit_chain_records_all(self, swarm):
        r = swarm.run("对合力砖厂做一次全套大气检查")
        tail = swarm.audit.tail(10)
        sources = [e["source"] for e in tail]
        for role in (*ROLE_ORDER, "synthesis"):
            assert f"swarm:{role}" in sources
        assert all(e["task_id"] == r["task_id"] for e in tail[-4:])
        assert swarm.audit.verify_chain()["valid"] is True

    def test_role_prompt_has_safety_layer_and_phase(self, swarm):
        swarm.run("对合力砖厂做一次全套大气检查")
        patrol_call = [c for c in swarm.client.calls if "现场巡查专家" in c["system"]][0]
        assert "安全准则" in patrol_call["system"]
        assert "现场巡查" in patrol_call["system"]  # 复用 inspection 阶段预设

    def test_format_result_marks_contributions(self, swarm):
        r = swarm.run("对合力砖厂做一次全套大气检查")
        text = swarm.format_result(r)
        for role in ROLE_ORDER:
            assert ROLES[role]["name"] in text
        assert "仲裁合成" in text

    def test_role_error_isolated(self, tmp_path):
        class FailClient(MockClient):
            def chat(self, messages, model="", stream=False, temperature=0.7):
                if "法规核验专家" in messages[0]["content"]:
                    raise RuntimeError("boom")
                return super().chat(messages, model=model)

        sw = RoleSwarm(client=FailClient(), audit_chain=PromptAuditChain(tmp_path / "a.jsonl"))
        r = sw.run("对合力砖厂做一次全套大气检查")
        assert r["errors"].get("law") == "boom"
        assert r["contributions"]["law"] == ""
        assert "[合成]" in r["synthesis"]  # 其余角色不受影响
