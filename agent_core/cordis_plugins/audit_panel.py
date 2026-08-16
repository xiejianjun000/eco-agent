#!/usr/bin/env python3
"""
agent_core/cordis_plugins/audit_panel.py — 审计链面板插件（Slot 演示）

注册 side.tab 面板「审计链」：数据来自 trace_audit（govmcp SM3 审计链
verify 结果 + 按操作类型统计），前端按通用表格渲染。

依赖 slots + trace_audit 服务（inject 声明，缺失时挂起）。
"""

from __future__ import annotations

import logging

logger = logging.getLogger("eco.plugin.audit_panel")


class AuditPanel:
    inject = ["slots", "trace_audit"]

    def apply(self, ctx, config: dict) -> None:
        slots = ctx.get("slots")

        def provider() -> dict:
            audit = ctx.get("trace_audit")
            verify = audit.verify()
            stats = audit.stats()
            return {
                "chain": verify,
                "stats": stats,
            }

        slots.register("side.tab", {
            "id": "audit-panel",
            "title": "审计链",
            "description": "govmcp SM3 审计链：完整性校验 + 调用统计",
            "provider": provider,
        })
        logger.info("audit_panel 面板已注册 side.tab")
