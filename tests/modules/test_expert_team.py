#!/usr/bin/env python3
"""expert_team 声明式领域专家团测试（LLM 层 mock）"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest
from agent_core.expert_team import (
    ExpertTeam, get_team, is_complex_task, list_teams, REGISTRY,
)
from agent_core.prompt_engine import PromptAuditChain


class MockClient:
    """mock LLMClient.chat：按 system 内容回显角色/专家标记"""
    def __init__(self):
        self.calls = []

    def chat(self, messages, model="", stream=False, temperature=0.7):
        system = messages[0]["content"]
        user = messages[-1]["content"]
        self.calls.append({"system": system, "user": user, "model": model})
        if "总管" in system:
            text = "[合成] 大气溯源研判报告（综合各方）"
        elif "现场巡查专家" in system:
            text = "[巡查] 现场检查要点与取证规范"
        elif "法规核验专家" in system:
            text = "[法规] 《大气污染防治法》第二十条"
        elif "执法文书专家" in system:
            text = "[文书] 检查记录框架与巡查清单"
        elif "数据接入" in system:
            text = "[数据接入] 站点清单与六参浓度"
        elif "污染指纹" in system:
            text = "[污染指纹] PM2.5/PM10 高，二次转化型"
        elif "传输轨迹" in system:
            text = "[传输轨迹] 主导来向西北，传输占比约 30%"
        elif "源解析" in system:
            text = "[源解析] 工业 35% / 扬尘 25% / 机动车 20%"
        elif "气象耦合" in system:
            text = "[气象耦合] 静稳逆温，利于累积"
        elif "空间格局" in system:
            text = "[空间格局] 本地高周边低，本地源主导"
        elif "历史同比" in system:
            text = "[历史同比] 同期偏高，异常过程"
        elif "成因研判" in system:
            text = "[成因研判] 主导成因：本地累积+二次转化，置信中"
        elif "管控建议" in system:
            text = "[管控建议] 扬尘管控+工业错峰"
        else:
            text = "[mock]"
        return {"choices": [{"message": {"content": text}}]}


@pytest.fixture()
def law_team(tmp_path):
    return ExpertTeam(get_team("law_enforcement"),
                     client=MockClient(), audit_chain=PromptAuditChain(tmp_path / "audit.jsonl"))


@pytest.fixture()
def air_team(tmp_path):
    return ExpertTeam(get_team("air_source"),
                     client=MockClient(), audit_chain=PromptAuditChain(tmp_path / "audit.jsonl"))


# ── 注册表 ──
class TestRegistry:
    def test_both_teams_registered(self):
        ids = {t.id for t in list_teams()}
        assert "law_enforcement" in ids
        assert "air_source" in ids

    def test_get_team_unknown(self):
        assert get_team("nope") is None


# ── 执法团队（行为应当与 RoleSwarm 一致）──
class TestLawTeam:
    def test_dag_all_roles_contribute(self, law_team):
        r = law_team.run("对合力砖厂做一次全套大气检查")
        spec = law_team.spec
        assert set(r["contributions"].keys()) == set(spec.role_order)
        assert "[巡查]" in r["contributions"]["patrol"]
        assert "[法规]" in r["contributions"]["law"]
        assert "[文书]" in r["contributions"]["doc"]
        assert "[合成]" in r["synthesis"]
        assert r["errors"] == {}
        assert r["task_id"]

    def test_doc_depends_on_patrol_and_law(self, law_team):
        law_team.run("对合力砖厂做一次全套大气检查")
        doc_call = [c for c in law_team.client.calls if "执法文书专家" in c["system"]][0]
        assert "[巡查]" in doc_call["user"]
        assert "[法规]" in doc_call["user"]

    def test_synthesis_gets_all_contributions(self, law_team):
        law_team.run("对合力砖厂做一次全套大气检查")
        synth_call = [c for c in law_team.client.calls if "总管" in c["system"]][0]
        for marker in ("[巡查]", "[法规]", "[文书]"):
            assert marker in synth_call["user"]

    def test_audit_chain_records_all(self, law_team):
        r = law_team.run("对合力砖厂做一次全套大气检查")
        tail = law_team.audit.tail(10)
        sources = [e["source"] for e in tail]
        for role in law_team.spec.role_order + ["synthesis"]:
            assert f"team:law_enforcement:{role}" in sources
        assert all(e["task_id"] == r["task_id"] for e in tail[-4:])
        assert law_team.audit.verify_chain()["valid"] is True

    def test_role_prompt_has_safety_layer_and_phase(self, law_team):
        law_team.run("对合力砖厂做一次全套大气检查")
        patrol_call = [c for c in law_team.client.calls if "现场巡查专家" in c["system"]][0]
        assert "安全准则" in patrol_call["system"]
        assert "现场巡查" in patrol_call["system"]

    def test_role_error_isolated(self, tmp_path):
        class FailClient(MockClient):
            def chat(self, messages, model="", stream=False, temperature=0.7):
                if "法规核验专家" in messages[0]["content"]:
                    raise RuntimeError("boom")
                return super().chat(messages, model=model)
        sw = ExpertTeam(get_team("law_enforcement"),
                        client=FailClient(), audit_chain=PromptAuditChain(tmp_path / "a.jsonl"))
        r = sw.run("对合力砖厂做一次全套大气检查")
        assert r["errors"].get("law") == "boom"
        assert r["contributions"]["law"] == ""
        assert "[合成]" in r["synthesis"]


# ── 大气溯源团队（新增，10-Agent 拓扑）──
class TestAirTeam:
    def test_all_roles_contribute(self, air_team):
        r = air_team.run("对长沙市做一次 PM2.5 污染溯源研判")
        spec = air_team.spec
        assert set(r["contributions"].keys()) == set(spec.role_order)
        assert len(spec.role_order) == 9  # 9 专家 + 1 总管合成 = 10-Agent
        assert "[合成]" in r["synthesis"]
        assert r["errors"] == {}

    def test_data_ingest_is_wave0_dependency(self, air_team):
        air_team.run("对长沙市做一次 PM2.5 污染溯源研判")
        finger_call = [c for c in air_team.client.calls if "污染指纹" in c["system"]][0]
        assert "[数据接入]" in finger_call["user"]  # 数据接入产出作为前置注入

    def test_causation_after_six_parallel_roles(self, air_team):
        r = air_team.run("对长沙市做一次 PM2.5 污染溯源研判")
        waves = r["waves"]
        assert "data_ingest" in waves[0]
        assert "causation" in waves[2]  # wave1=6 并行角色, wave2=成因研判
        assert "control_advice" in waves[3]

    def test_audit_chain_records_all(self, air_team):
        r = air_team.run("对长沙市做一次 PM2.5 污染溯源研判")
        tail = air_team.audit.tail(20)
        sources = [e["source"] for e in tail]
        for role in air_team.spec.role_order + ["synthesis"]:
            assert f"team:air_source:{role}" in sources
        assert air_team.audit.verify_chain()["valid"] is True

    def test_is_complex_task_air(self):
        spec = get_team("air_source")
        assert is_complex_task(spec, "对长沙市做一次 PM2.5 污染溯源研判") is True
        assert is_complex_task(spec, "今天空气质量怎么样") is False


if __name__ == "__main__":
    # 无 pytest 时的极简自检
    import tempfile
    for tid in ("law_enforcement", "air_source"):
        t = ExpertTeam(get_team(tid), client=MockClient(),
                       audit_chain=PromptAuditChain(Path(tempfile.mkdtemp()) / "a.jsonl"))
        r = t.run("对长沙市做一次 PM2.5 污染溯源研判" if tid == "air_source"
                  else "对合力砖厂做一次全套大气检查")
        assert set(r["contributions"].keys()) == set(t.spec.role_order)
        assert "[合成]" in r["synthesis"]
        assert r["errors"] == {}
        assert t.audit.verify_chain()["valid"] is True
        print(f"OK {tid}: {len(t.spec.role_order)} 角色, waves={r['waves']}")
    print("ALL OK")
