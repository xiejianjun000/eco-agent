# -*- coding: utf-8 -*-
"""RBAC 角色矩阵测试：矩阵判定 / 默认关闭兼容 / grant 角色流 / 篡改容错"""
import json

import pytest

from agent_core import grants as grants_mod
from agent_core import rbac
from agent_core.rbac import Capability, Role
from eco.commands import cmd_auth


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("ECO_RBAC", raising=False)
    monkeypatch.delenv("ECO_ROLE", raising=False)
    monkeypatch.delenv("ECO_AUTH_ROLE", raising=False)


@pytest.fixture()
def grants_env(tmp_path, monkeypatch):
    gdir = tmp_path / "grants"
    monkeypatch.setattr(grants_mod, "GRANTS_DIR", gdir)
    monkeypatch.setattr(grants_mod, "SECRET_FILE", tmp_path / "grant_secret")
    return gdir


class _Args:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class TestMatrix:
    def test_admin_has_all_capabilities(self):
        for cap in Capability:
            assert rbac.check(Role.ADMIN, cap)

    def test_commander_no_workspace_admin(self):
        assert rbac.check(Role.COMMANDER, Capability.AUTH_GRANT)
        assert rbac.check(Role.COMMANDER, Capability.EVOLUTION)
        assert not rbac.check(Role.COMMANDER, Capability.WORKSPACE_ADMIN)

    def test_enforcer_limited(self):
        assert rbac.check(Role.ENFORCER, Capability.CHAT)
        assert rbac.check(Role.ENFORCER, Capability.CORRECTIONS)
        assert not rbac.check(Role.ENFORCER, Capability.AUTH_GRANT)
        assert not rbac.check(Role.ENFORCER, Capability.EVOLUTION)
        assert not rbac.check(Role.ENFORCER, Capability.CHANNEL_MANAGE)

    def test_auditor_readonly_trace(self):
        assert rbac.check(Role.AUDITOR, Capability.TRACE_EXPORT)
        assert not rbac.check(Role.AUDITOR, Capability.CORRECTIONS)
        assert not rbac.check(Role.AUDITOR, Capability.AUTH_GRANT)

    def test_visitor_chat_only(self):
        assert rbac.check(Role.READONLY_VISITOR, Capability.CHAT)
        for cap in Capability:
            if cap is not Capability.CHAT:
                assert not rbac.check(Role.READONLY_VISITOR, cap)

    def test_string_role_and_capability(self):
        assert rbac.check("admin", "chat")
        assert rbac.check("执法员", "corrections")
        assert rbac.check("指挥长", "auth_grant")
        assert not rbac.check("审计员", "evolution")

    def test_unknown_role_denied(self):
        assert not rbac.check("superroot", Capability.CHAT)
        assert not rbac.check(None, Capability.CHAT)

    def test_unknown_capability_denied(self):
        assert not rbac.check(Role.ADMIN, "delete_everything")


class TestGateCompat:
    def test_default_disabled_allows_everything(self):
        # ECO_RBAC 默认关闭：任何能力一律放行（保持兼容）
        assert not rbac.rbac_enabled()
        assert rbac.require_capability(Capability.WORKSPACE_ADMIN)
        assert rbac.require_capability("auth_grant")

    def test_enabled_without_role_denies(self, monkeypatch):
        monkeypatch.setenv("ECO_RBAC", "1")
        assert rbac.rbac_enabled()
        assert not rbac.require_capability(Capability.CHAT)

    def test_enabled_with_session_role(self, monkeypatch):
        monkeypatch.setenv("ECO_RBAC", "1")
        monkeypatch.setenv("ECO_ROLE", "审计员")
        assert rbac.session_role() is Role.AUDITOR
        assert rbac.require_capability(Capability.TRACE_EXPORT)
        assert not rbac.require_capability(Capability.AUTH_GRANT)

    def test_enabled_explicit_role_arg(self, monkeypatch):
        monkeypatch.setenv("ECO_RBAC", "1")
        assert rbac.require_capability(Capability.EVOLUTION, role="指挥长")
        assert not rbac.require_capability(Capability.WORKSPACE_ADMIN, role="指挥长")

    def test_capabilities_of(self):
        caps = rbac.capabilities_of("readonly_visitor")
        assert caps == frozenset({Capability.CHAT})
        assert rbac.capabilities_of("nobody") == frozenset()


class TestGrantRoleFlow:
    def test_grant_with_role_signed_and_listed(self, grants_env):
        g = rbac.grant_with_role(level="L4", ttl=600, role="执法员")
        assert g["role"] == "执法员"
        listed = grants_mod.list_grants()
        assert len(listed) == 1
        assert listed[0]["role"] == "执法员"
        assert listed[0]["_valid_sig"]  # role 参与签名，验签通过

    def test_grant_without_role_compatible(self, grants_env):
        g = rbac.grant_with_role(level="L3", ttl=60)
        assert "role" not in g
        assert grants_mod.list_grants()[0]["_valid_sig"]

    def test_grant_unknown_role_rejected(self, grants_env):
        with pytest.raises(ValueError):
            rbac.grant_with_role(role="皇帝")

    def test_grant_rbac_gate(self, grants_env, monkeypatch):
        monkeypatch.setenv("ECO_RBAC", "1")
        monkeypatch.setenv("ECO_ROLE", "审计员")  # 无 auth_grant 能力
        with pytest.raises(PermissionError):
            rbac.grant_with_role(role="执法员")
        monkeypatch.setenv("ECO_ROLE", "指挥长")
        g = rbac.grant_with_role(role="执法员")
        assert g["role"] == "执法员"

    def test_tampered_role_breaks_signature(self, grants_env):
        g = rbac.grant_with_role(level="L4", ttl=600, role="执法员")
        p = grants_env / f"{g['id']}.json"
        body = json.loads(p.read_text(encoding="utf-8"))
        body["role"] = "admin"  # 篡改角色提权
        p.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
        assert not grants_mod.list_grants()[0]["_valid_sig"]

    def test_cmd_auth_grant_with_role(self, grants_env, capsys):
        rc = cmd_auth.run(_Args(auth_action="grant", level="L4", ttl=300,
                                scope="*", role="审计员"))
        assert rc == 0
        out = capsys.readouterr().out
        assert "role=审计员" in out
        assert grants_mod.list_grants()[0]["role"] == "审计员"

    def test_cmd_auth_grant_role_from_env(self, grants_env, monkeypatch, capsys):
        monkeypatch.setenv("ECO_AUTH_ROLE", "readonly_visitor")
        rc = cmd_auth.run(_Args(auth_action="grant", level="L4", ttl=300, scope="*"))
        assert rc == 0
        assert grants_mod.list_grants()[0]["role"] == "readonly_visitor"

    def test_cmd_auth_grant_denied_by_rbac(self, grants_env, monkeypatch, capsys):
        monkeypatch.setenv("ECO_RBAC", "1")
        monkeypatch.setenv("ECO_ROLE", "执法员")  # 无 auth_grant 能力
        rc = cmd_auth.run(_Args(auth_action="grant", level="L4", ttl=300,
                                scope="*", role="执法员"))
        assert rc == 1
        assert "拒绝" in capsys.readouterr().out
        assert grants_mod.list_grants() == []

    def test_cmd_auth_list_shows_role(self, grants_env, capsys):
        rbac.grant_with_role(level="L4", ttl=600, role="指挥长")
        rc = cmd_auth.run(_Args(auth_action="list"))
        assert rc == 0
        out = capsys.readouterr().out
        assert "role=指挥长" in out and "有效" in out
