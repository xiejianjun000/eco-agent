"""国内通讯渠道网关（模块 B）。

导出统一消息模型、抽象基类、注册表与全流程入口。
"""
from .base import (BLOCK_TEXT, VERIFY_FAIL_TEXT, Channel, InboundMessage)
from .registry import CHANNELS, get_channel, handle_inbound

__all__ = [
    "InboundMessage", "Channel", "BLOCK_TEXT", "VERIFY_FAIL_TEXT",
    "CHANNELS", "get_channel", "handle_inbound",
]
