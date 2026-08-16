#!/usr/bin/env python3
"""
server/__init__.py
ECO AGENT 管理 API 服务（eco-server）

面向应用的 REST/SSE API：对话、会话、记忆树、技能、工具目录、系统指标。
与 gateway/（通道 webhook）互补：gateway 面向聊天平台，server 面向应用与 Web GUI。
"""

__all__ = ["create_app", "get_version"]

from server.app import create_app, get_version
