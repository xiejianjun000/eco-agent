#!/usr/bin/env python3
"""
agent_core/cordis_plugins/govmcp_tools_loader.py — 政务平台工具集插件
====================================================================
对标 DSH「一切皆插件」：新增/下线政务平台工具 = 本文件/组合清单，
不改 server/chat.py 硬编码。

apply(ctx, config)：把 govmcp 五平台（wryzxjc/sthjzf/permit/env_open_data/
hunan_env）的 CHAT_TOOLS 批量注册进 tools_registry 并挂进聊天工具表。
与 chat._ensure_platform_tools 幂等共存（双保险：独立脚本不依赖 cordis）。
"""

from __future__ import annotations

import logging

logger = logging.getLogger("eco.cordis.govmcp_tools")


def apply(ctx, config: dict | None = None) -> None:
    """组合装配入口：注册政务平台工具（幂等）。"""
    from agent_core.tools_registry import register_external_tool
    from govmcp_tools import env_open_data, hunan_env, permit_management, sthjzf, wryzxjc

    registered: list[str] = []
    for mod in (wryzxjc, sthjzf, permit_management, env_open_data, hunan_env):
        from agent_core.tools_registry import _HANDLERS as _EXISTING

        for name, spec in getattr(mod, "CHAT_TOOLS", {}).items():
            if name in _EXISTING:
                continue  # 已注册（boot 阶段或上轮装配）：幂等跳过，不算失败
            try:
                register_external_tool(
                    name,
                    spec["description"],
                    spec["parameters"],
                    spec["handler"],
                    level="L1",
                    category="政务平台",
                )
                registered.append(name)
            except Exception as e:  # noqa: BLE001 — 幂等/重复注册不阻断组合装配
                logger.debug("[govmcp_tools_loader] %s 注册跳过: %s", name, e)
    if registered:
        # 挂进聊天工具表（与 chat._ensure_platform_tools 同一集合，幂等去重）
        try:
            from server.api import chat

            for name in registered:
                if name not in chat._PLATFORM_CHAT_NAMES:
                    chat._PLATFORM_CHAT_NAMES.append(name)
            for mod in (wryzxjc, sthjzf, permit_management, env_open_data, hunan_env):
                for name, spec in getattr(mod, "CHAT_TOOLS", {}).items():
                    if name not in [d.get("name") for d in chat._PLATFORM_CHAT_DEFS]:
                        chat._PLATFORM_CHAT_DEFS.append(
                            {
                                "type": "function",
                                "function": {
                                    "name": name,
                                    "description": spec["description"],
                                    "parameters": spec["parameters"],
                                },
                            }
                        )
        except Exception:  # noqa: BLE001 — 服务端模块未就绪时不挂聊天表
            pass
    logger.info("[govmcp_tools_loader] 组合装配注册 %d 个政务平台工具: %s", len(registered), registered[:6])
