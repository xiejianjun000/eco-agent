"""SOUL 接线 + L1-L4 权限闸门测试（离线，mock LLM/审计链）"""
import json

import pytest

from agent_core.prompt_engine import (PromptAuditChain, PromptEngine,
                                      SAFETY_LAYER, _reset_engine_for_test)
from agent_core import soul as soul_mod


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """审计链与 SOUL 缓存隔离到 tmp；profiles 指向仓内真实 profiles；
    审批栈单例隔离到 tmp（避免写 ~/.eco）"""
    monkeypatch.setenv("ECO_PERMISSION_GATE", "1")
    monkeypatch.setenv("ECO_NONINTERACTIVE", "1")
    from agent_core import approval as approval_mod
    monkeypatch.setattr(approval_mod, "_service",
                        approval_mod.ApprovalService(policy="ask", answerers=["tester"],
                                                     path=tmp_path / "approvals.jsonl"))
    soul_mod._reset_for_test()
    _reset_engine_for_test()
    yield
    soul_mod._reset_for_test()
    _reset_engine_for_test()


def _engine(tmp_path) -> PromptEngine:
    return PromptEngine(audit_chain=PromptAuditChain(tmp_path / "audit.jsonl"))


# ── SOUL 接线 ─────────────────────────────────────────────

class TestSoulLoading:
    def test_soul_file_found_and_parsed(self):
        s = soul_mod.load_soul()
        assert s.loaded
        assert "硬边界" in s.sections
        assert "置信度" in s.persona_prompt  # 沟通风格段落
        assert "绝不编造信息" in s.hard_boundaries

    def test_system_prompt_contains_persona_and_boundaries(self, tmp_path):
        eng = _engine(tmp_path)
        prompt = eng.build_system_prompt()
        assert prompt.startswith("【安全准则")          # 安全层首位不可动摇
        assert "SOUL 硬边界" in prompt                   # 硬边界并入安全层
        assert "置信度" in prompt                        # 人格层进入系统提示词
        assert SAFETY_LAYER in prompt                    # 硬编码兜底仍在

    def test_missing_soul_fallback(self, tmp_path, monkeypatch):
        """SOUL.md 缺失：回退硬编码，不崩"""
        monkeypatch.setenv("ECO_PROFILES_DIR", str(tmp_path / "empty"))
        monkeypatch.setattr(soul_mod, "_REPO_PROFILES", tmp_path / "nope")
        monkeypatch.setattr(soul_mod.Path, "home", staticmethod(lambda: tmp_path))
        s = soul_mod.load_soul(force_reload=True)
        assert not s.loaded
        eng = _engine(tmp_path)
        eng.soul = s
        prompt = eng.build_system_prompt()
        assert SAFETY_LAYER in prompt
        assert "SOUL 硬边界" not in prompt
        assert "你是 eco Agent" in prompt  # 硬编码人格兜底

    def test_soul_edit_takes_effect_after_reload(self, tmp_path, monkeypatch):
        """修改 SOUL.md 边界 -> reload 后系统提示词生效（验证项 c 的单测形态）"""
        s = soul_mod.load_soul()
        marker = "临时规则XYZ：测试期间所有回答以【测试模式】开头"
        patched = s.raw.replace("## 硬边界", f"## 硬边界\n\n0. **{marker}**", 1)
        eng = _engine(tmp_path)
        eng.soul = soul_mod.Soul(patched)
        assert marker in eng.build_system_prompt()
        # 改回后消失
        eng.soul = s
        assert marker not in eng.build_system_prompt()

    def test_cmd_chat_uses_prompt_engine(self, tmp_path):
        from eco.commands.cmd_chat import _build_messages
        msgs = _build_messages([], "测试问题")
        system = msgs[0]["content"]
        assert system.startswith("【安全准则")
        assert "置信度" in system

    def test_role_swarm_merges_agent_soul(self):
        from agent_core.role_swarm import RoleSwarm, ROLES
        swarm = RoleSwarm.__new__(RoleSwarm)  # 不触发 LLM client
        prompt = swarm._role_system_prompt("patrol")
        assert "searcher" in ROLES["patrol"]["soul"]
        assert "角色人格 searcher_soul" in prompt     # soul 文件内容已合并
        assert ROLES["patrol"]["brief"] in prompt     # 硬编码 brief 兜底保留
        assert "【安全准则" in prompt

    def test_role_swarm_fallback_when_soul_missing(self, monkeypatch):
        from agent_core.role_swarm import RoleSwarm, ROLES
        monkeypatch.setattr(soul_mod, "_find_file", lambda rel: None)
        prompt = RoleSwarm.__new__(RoleSwarm)._role_system_prompt("law")
        assert "角色人格" not in prompt
        assert ROLES["law"]["brief"] in prompt


# ── 权限闸门 ─────────────────────────────────────────────

class TestPermissions:
    def test_default_risk_mapping(self):
        from agent_core.permissions import tool_risk_level
        assert tool_risk_level("query_air_quality") == "L1"
        assert tool_risk_level("search_regulation") == "L1"
        assert tool_risk_level("generate_carbon_emission_report") == "L2"
        assert tool_risk_level("execute_code") == "L3"
        assert tool_risk_level("apply_invoice") == "L4"
        assert tool_risk_level("trade_carbon_emission_allowance") == "L4"
        assert tool_risk_level("totally_unknown_tool") == "L3"  # 未知保守 L3

    def test_permission_md_override(self):
        from agent_core.permissions import load_overrides, tool_risk_level
        overrides = load_overrides()
        assert overrides.get("execute_code") == "L3"
        assert overrides.get("generate_approval_document") == "L4"
        assert tool_risk_level("generate_approval_document", overrides) == "L4"

    def test_l1_auto_allow_and_audit(self, tmp_path, monkeypatch):
        eng = _engine(tmp_path)
        monkeypatch.setattr("agent_core.prompt_engine._engine", eng)
        from agent_core.permissions import gate_tool_call
        ok, level, reason = gate_tool_call("query_air_quality", {"city": "北京"})
        assert ok and level == "L1"
        entries = eng.audit.tail(1)
        assert entries[0]["source"] == "permission"
        assert entries[0]["accepted"] is True
        assert "query_air_quality" in entries[0]["content"]

    def test_l4_noninteractive_submits_pending_and_audited(self, tmp_path, monkeypatch):
        """L4 无 grant 且非交互：登记审批栈 pending（不再是单纯 deny），审计对落链"""
        eng = _engine(tmp_path)
        monkeypatch.setattr("agent_core.prompt_engine._engine", eng)
        from agent_core.permissions import gate_tool_call
        ok, level, reason = gate_tool_call("apply_invoice", {"company": "X"})
        assert not ok and level == "L4"
        assert "审批请求" in reason and "pending:" in reason
        # asked（approval）+ 闸门决策（permission，pending 未放行）
        entries = eng.audit.tail(2)
        srcs = [e["source"] for e in entries]
        assert srcs == ["approval", "permission"]
        perm_entry = entries[-1]
        assert perm_entry["accepted"] is False

    def test_l4_interactive_confirm_paths(self, tmp_path, monkeypatch):
        """交互模式：y 放行 / n 拒绝 两条路径"""
        eng = _engine(tmp_path)
        monkeypatch.setattr("agent_core.prompt_engine._engine", eng)
        monkeypatch.setenv("ECO_NONINTERACTIVE", "0")
        import agent_core.permissions as perm
        monkeypatch.setattr(perm, "_is_interactive", lambda: True)
        monkeypatch.setattr("builtins.input", lambda prompt="": "y")
        ok, _, reason = perm.gate_tool_call("apply_invoice", {})
        assert ok and "审批放行" in reason
        monkeypatch.setattr("builtins.input", lambda prompt="": "n")
        ok, _, reason = perm.gate_tool_call("apply_invoice", {})
        assert not ok and "审批拒绝" in reason
        srcs = [e["source"] for e in eng.audit.tail(2)]
        assert srcs == ["permission", "permission"]

    def test_l3_whitelist_and_nonwhitelist(self, tmp_path, monkeypatch):
        eng = _engine(tmp_path)
        monkeypatch.setattr("agent_core.prompt_engine._engine", eng)
        from agent_core.permissions import gate_tool_call
        ok, _, reason = gate_tool_call("execute_code", {"command": "git status"})
        assert ok and "白名单" in reason
        ok, _, _ = gate_tool_call("execute_code", {"command": "rm -rf /"})
        assert not ok  # 非白名单 + 非交互 -> 拒绝

    def test_execute_tool_gate_blocks_l4(self, tmp_path, monkeypatch):
        import asyncio
        eng = _engine(tmp_path)
        monkeypatch.setattr("agent_core.prompt_engine._engine", eng)
        from agent_core.tools_registry import execute_tool
        result = json.loads(asyncio.run(execute_tool("apply_invoice", {"company": "X"})))
        assert "permission denied" in result["error"]
        assert result["permission"]["level"] == "L4"

    def test_execute_tool_gate_passes_l1(self, tmp_path, monkeypatch):
        import asyncio
        eng = _engine(tmp_path)
        monkeypatch.setattr("agent_core.prompt_engine._engine", eng)
        from agent_core.tools_registry import execute_tool
        result = json.loads(asyncio.run(execute_tool("query_air_quality", {"city": "北京"})))
        assert "permission denied" not in json.dumps(result, ensure_ascii=False)

    def test_risk_table_covers_all_tools(self):
        from agent_core.permissions import risk_table, LEVELS
        from agent_core import tools_registry as tr
        table = risk_table()
        # 覆盖全部 LLM 可见工具（白名单瘦身后 5 内置 + 外部注册）
        visible = tr.get_tool_names()
        missing = [n for n in visible if n not in table]
        assert missing == [], f"风险表未覆盖工具: {missing}"
        assert all(lv in LEVELS for lv in table.values())
