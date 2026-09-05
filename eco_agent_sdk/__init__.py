#!/usr/bin/env python3
"""
eco_agent_sdk — ECO AGENT 官方 Python SDK

面向应用的客户端：对接 eco-server 管理 API（chat/sessions/memory/skills/tools/system）。
异步（httpx.AsyncClient）与同步（SyncEcoClient 包装）双形态。

用法:
    from eco_agent_sdk import EcoClient

    client = EcoClient("http://127.0.0.1:8788")
    resp = await client.chat("违反大气污染防治法的处罚幅度是多少？")
    print(resp.reply)
"""

from eco_agent_sdk.client import EcoClient, SyncEcoClient
from eco_agent_sdk.errors import EcoApiError, EcoConnectionError, EcoError
from eco_agent_sdk.types import (
    ChatRequest,
    ChatResponse,
    MemoryNode,
    MemoryStats,
    SessionInfo,
    SkillInfo,
    SystemStatus,
    ToolEntry,
    VersionInfo,
)

__version__ = "1.0.0"

__all__ = [
    "EcoClient",
    "SyncEcoClient",
    "EcoError",
    "EcoConnectionError",
    "EcoApiError",
    "ChatRequest",
    "ChatResponse",
    "MemoryNode",
    "MemoryStats",
    "SessionInfo",
    "SkillInfo",
    "SystemStatus",
    "ToolEntry",
    "VersionInfo",
    "__version__",
]
