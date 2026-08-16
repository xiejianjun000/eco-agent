#!/usr/bin/env python3
"""
agent_core/cordis/boot.py — 应用上下文装配（server 启动时装载）
"""

from __future__ import annotations

import logging
from pathlib import Path

from agent_core.cordis import Context, load_composition
from agent_core.cordis.services import register_standard_services

logger = logging.getLogger("eco.cordis.boot")

ROOT = Path(__file__).resolve().parent.parent.parent

_app_ctx: Context | None = None


def get_app_context() -> Context:
    """进程级应用组合上下文（服务 + 组合插件）。"""
    global _app_ctx
    if _app_ctx is None:
        ctx = Context(name="eco-app")
        register_standard_services(ctx)
        yml = ROOT / "eco.cordis.yml"
        if yml.is_file():
            try:
                load_composition(str(yml), ctx=ctx)
            except Exception:  # noqa: BLE001 — 组合装配失败不阻断 API
                logger.exception("组合装配失败: %s", yml)
        _app_ctx = ctx
        logger.info("cordis 应用上下文已装配: %s", ctx.snapshot())
    return _app_ctx
