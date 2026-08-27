#!/usr/bin/env python3
"""rbac.py — RBAC 角色矩阵（SSO 前置）

角色 × 能力 静态矩阵 + 会话角色绑定：
  - Role 枚举：admin / 指挥长 / 执法员 / 审计员 / readonly_visitor
  - PERMISSION_MATRIX：角色 × 能力（chat/evolution/auth grant/corrections/
    workspace admin/trace export/channel manage）
  - check(role, capability)：矩阵判定（未知角色/能力一律拒绝）
  - 会话角色绑定：环境变量 ECO_ROLE 绑定当前会话角色
  - 开关：ECO_RBAC=1 启用；默认关闭，require_capability() 一律放行，保持兼容

授权令牌角色维度：grant_with_role() 在 grants.grant 基础上附加 role 字段
并就地重签名（不修改 grants.py，签名体含 role，防篡改）。
"""
from __future__ import annotations

import json
import os
from enum import Enum
from pathlib import Path

from agent_core import grants as grants_mod


class Role(str, Enum):
    ADMIN = "admin"
    COMMANDER = "指挥长"
    ENFORCER = "执法员"
    AUDITOR = "审计员"
    READONLY_VISITOR = "readonly_visitor"


class Capability(str, Enum):
    CHAT = "chat"
    EVOLUTION = "evolution"
    AUTH_GRANT = "auth_grant"
    CORRECTIONS = "corrections"
    WORKSPACE_ADMIN = "workspace_admin"
    TRACE_EXPORT = "trace_export"
    CHANNEL_MANAGE = "channel_manage"


_ALL_CAPS = frozenset(Capability)

PERMISSION_MATRIX: dict[Role, frozenset[Capability]] = {
    Role.ADMIN: _ALL_CAPS,
    Role.COMMANDER: frozenset({
        Capability.CHAT, Capability.EVOLUTION, Capability.AUTH_GRANT,
        Capability.CORRECTIONS, Capability.TRACE_EXPORT, Capability.CHANNEL_MANAGE,
    }),
    Role.ENFORCER: frozenset({
        Capability.CHAT, Capability.CORRECTIONS, Capability.TRACE_EXPORT,
    }),
    Role.AUDITOR: frozenset({
        Capability.CHAT, Capability.TRACE_EXPORT,
    }),
    Role.READONLY_VISITOR: frozenset({Capability.CHAT}),
}


def _coerce_role(role) -> Role | None:
    if isinstance(role, Role):
        return role
    if isinstance(role, str):
        for r in Role:
            if role in (r.value, r.name, r.name.lower()):
                return r
    return None


def _coerce_cap(capability) -> Capability | None:
    if isinstance(capability, Capability):
        return capability
    if isinstance(capability, str):
        for c in Capability:
            if capability in (c.value, c.name, c.name.lower()):
                return c
    return None


def check(role, capability) -> bool:
    """矩阵判定：角色是否拥有能力。未知角色/能力 → False。接受枚举或字符串。"""
    r = _coerce_role(role)
    c = _coerce_cap(capability)
    if r is None or c is None:
        return False
    return c in PERMISSION_MATRIX.get(r, frozenset())


def rbac_enabled() -> bool:
    return os.environ.get("ECO_RBAC", "").strip() in ("1", "true", "yes", "on")


def session_role() -> Role | None:
    """当前会话绑定角色（env ECO_ROLE）；未绑定/非法 → None"""
    return _coerce_role(os.environ.get("ECO_ROLE", ""))


def require_capability(capability, role=None) -> bool:
    """能力闸门：ECO_RBAC 未启用 → 一律放行（默认兼容）。
    启用后按 role（缺省取会话角色）查矩阵；无绑定角色 → 拒绝。"""
    if not rbac_enabled():
        return True
    r = _coerce_role(role) if role is not None else session_role()
    if r is None:
        return False
    return check(r, capability)


def capabilities_of(role) -> frozenset[Capability]:
    r = _coerce_role(role)
    return PERMISSION_MATRIX.get(r, frozenset())


def grant_with_role(level: str = "L4", ttl: int = 3600, scope: str = "*",
                    role=None, grants_dir: Path | None = None) -> dict:
    """签发带角色维度的授权令牌：在 grants.grant 基础上附加 role 并重签名。
    ECO_RBAC 启用时，调用方会话角色须具备 auth_grant 能力。"""
    if not require_capability(Capability.AUTH_GRANT):
        raise PermissionError("当前会话角色无 auth grant 能力（ECO_RBAC=1）")
    r = _coerce_role(role) if role else None
    if role and r is None:
        raise ValueError(f"未知角色: {role}")
    g = grants_mod.grant(level=level, ttl=ttl, scope=scope, grants_dir=grants_dir)
    if r is not None:
        g["role"] = r.value
        g["signature"] = grants_mod._sign(
            {k: v for k, v in g.items() if k != "signature"})
        d = Path(grants_dir) if grants_dir else grants_mod.GRANTS_DIR
        (d / f"{g['id']}.json").write_text(
            json.dumps(g, ensure_ascii=False, indent=1), encoding="utf-8")
    return g
