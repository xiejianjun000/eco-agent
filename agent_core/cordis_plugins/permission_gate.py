#!/usr/bin/env python3
"""
agent_core/cordis_plugins/permission_gate.py — 权限闸门服务插件
====================================================================
把 L1-L4 权限闸门注册为 cordis 服务（permission_gate），与审计链（trace_audit）、
记忆树（memory_tree）并列——「权限/审计/记忆」三服务联动，对齐 DSH 三插件协作：
  权限闸门 → 审计链（SM3，source=permission）
  权限闸门 → 记忆树（recordDeniedToMemory，ctx.get 可选服务）
  其他插件 → ctx.get('permission_gate').gate_tool_call(...)
"""

from __future__ import annotations

import logging

logger = logging.getLogger("eco.cordis.permission_gate")


def apply(ctx, config: dict | None = None) -> None:
    from agent_core import permissions

    ctx.provide("permission_gate", {
        "gate_tool_call": permissions.gate_tool_call,
        "tool_risk_level": permissions.tool_risk_level,
        "load_overrides": permissions.load_overrides,
        "load_glob_rules": permissions.load_glob_rules,
        "load_l3_whitelist": permissions.load_l3_whitelist,
    })
    logger.info("[permission_gate] 权限闸门服务已注册（permission_gate）")
