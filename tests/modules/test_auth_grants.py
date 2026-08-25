"""非交互 L4 授权令牌测试：无 grant 阻断 / grant 放行+审计 / 过期拒绝 / 篡改拒绝"""
import json

import pytest

from agent_core import grants as grants_mod
from agent_core.permissions import gate_tool_call

L4_TOOL = "submit_report"  # submit_ 前缀 → L4/EXTERNAL


@pytest.fixture()
def grants_env(tmp_path, monkeypatch):
    """隔离授权目录与签名密钥到 tmp_path；审批栈单例也隔离到 tmp（避免写 ~/.eco）"""
    gdir = tmp_path / "grants"
    monkeypatch.setattr(grants_mod, "GRANTS_DIR", gdir)
    monkeypatch.setattr(grants_mod, "SECRET_FILE", tmp_path / "grant_secret")
    from agent_core import approval as approval_mod
    monkeypatch.setattr(approval_mod, "_service",
                        approval_mod.ApprovalService(policy="ask", answerers=["tester"],
                                                     path=tmp_path / "approvals.jsonl"))
    monkeypatch.setenv("ECO_NONINTERACTIVE", "1")  # 强制非交互（无 tty 也能走 grant 通道）
    monkeypatch.delenv("ECO_PERMISSION_GATE", raising=False)
    return gdir


def _read_audit_sources():
    from agent_core.prompt_engine import AUDIT_FILE
    if not AUDIT_FILE.exists():
        return []
    out = []
    for line in AUDIT_FILE.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line).get("source", ""))
            except json.JSONDecodeError:
                pass
    return out


class TestAuthGrants:
    def test_no_grant_blocks_l4(self, grants_env):
        ok, level, reason = gate_tool_call(L4_TOOL, {})
        assert not ok and level == "L4"
        # 无 grant 且非交互：不再单纯 deny，而是登记审批栈 pending 请求
        assert "审批请求" in reason and "pending:" in reason

    def test_grant_allows_and_audits(self, grants_env):
        g = grants_mod.grant(level="L4", ttl=3600, scope="*")
        assert (grants_env / f"{g['id']}.json").exists()
        ok, level, reason = gate_tool_call(L4_TOOL, {})
        assert ok and level == "L4"
        assert f"grant:{g['id']}" in reason
        # 审计留痕：source=grant:<id>
        sources = _read_audit_sources()
        assert any(s == f"grant:{g['id']}" for s in sources), sources[-5:]

    def test_expired_grant_denied(self, grants_env):
        grants_mod.grant(level="L4", ttl=-10, scope="*")  # 立即过期
        ok, _level, reason = gate_tool_call(L4_TOOL, {})
        assert not ok
        assert "审批请求" in reason

    def test_tampered_grant_denied(self, grants_env):
        g = grants_mod.grant(level="L4", ttl=3600, scope="*")
        p = grants_env / f"{g['id']}.json"
        data = json.loads(p.read_text(encoding="utf-8"))
        data["scope"] = "hacked" if g["scope"] != "hacked" else "xxx"  # 改一字节级篡改
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        ok, _level, _reason = gate_tool_call(L4_TOOL, {})
        assert not ok
        g2, why = grants_mod.find_valid_grant("L4", L4_TOOL)
        assert g2 is None and "篡改" in why

    def test_scope_mismatch_denied(self, grants_env):
        grants_mod.grant(level="L4", ttl=3600, scope="other_tool")
        ok, _level, _reason = gate_tool_call(L4_TOOL, {})
        assert not ok

    def test_revoke(self, grants_env):
        g = grants_mod.grant(level="L4", ttl=3600)
        assert grants_mod.revoke(g["id"])
        ok, _level, _reason = gate_tool_call(L4_TOOL, {})
        assert not ok
        assert not grants_mod.revoke("nonexistent")

    def test_l3_grant_cannot_cover_l4(self, grants_env):
        grants_mod.grant(level="L3", ttl=3600, scope="*")
        ok, level, _reason = gate_tool_call(L4_TOOL, {})
        assert not ok and level == "L4"

    def test_list_grants_marks_expired_and_sig(self, grants_env):
        g1 = grants_mod.grant(level="L4", ttl=3600)
        grants_mod.grant(level="L4", ttl=-1)
        gs = grants_mod.list_grants()
        assert len(gs) == 2
        by_id = {g["id"]: g for g in gs}
        assert by_id[g1["id"]]["_valid_sig"] and not by_id[g1["id"]]["_expired"]


class TestAuthCLI:
    def test_cli_grant_list_revoke(self, grants_env, capsys):
        from eco.commands import cmd_auth

        class A:
            auth_action = "grant"; level = "L4"; ttl = 600; scope = "*"; grant_id = None
        assert cmd_auth.run(A()) == 0
        out = capsys.readouterr().out
        gid = out.split("授权令牌")[1].split()[0].strip()

        class L:
            auth_action = "list"; grant_id = None
        assert cmd_auth.run(L()) == 0
        assert gid in capsys.readouterr().out

        class R:
            auth_action = "revoke"; grant_id = gid
        assert cmd_auth.run(R()) == 0
        assert not grants_mod.list_grants()
