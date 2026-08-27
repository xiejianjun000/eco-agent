"""渠道注册表与统一入口。

handle_inbound(name, request) 全流程：
  verify → parse → validate_injection 注入检查 → 返回待回复文本（供 gateway HTTP 层调用）
  - 验签失败 → VERIFY_FAIL_TEXT
  - 注入拦截 → BLOCK_TEXT（固定话术，不进入 chat 管道）
  - 飞书 url_verification → 回 {"challenge": ...} JSON 字符串
  - 企业微信/公众号 URL 验证(GET) → 回解密后的 echostr
"""
from __future__ import annotations

import json
from typing import Optional

from .base import BLOCK_TEXT, VERIFY_FAIL_TEXT, Channel
from .dingtalk import DingTalkChannel
from .feishu import FeishuChannel
from .qqbot import QQBotChannel
from .webhook import WebhookChannel
from .wechat_oa import WeChatOAChannel
from .wecom import WeComChannel

CHANNELS: dict[str, type[Channel]] = {
    c.name: c for c in (WeComChannel, DingTalkChannel, FeishuChannel,
                        QQBotChannel, WeChatOAChannel, WebhookChannel)
}

#: 进程级渠道实例缓存（config 不变时复用）
_instances: dict[str, Channel] = {}


def get_channel(name: str, config: dict | None = None) -> Channel:
    """按名取渠道实例；找不到抛 KeyError 并列出可用名。"""
    cls = CHANNELS.get(name)
    if cls is None:
        raise KeyError(
            f"未知渠道: {name!r}，可用: {', '.join(sorted(CHANNELS))}")
    if config is not None:
        return cls(config)
    if name not in _instances:
        _instances[name] = cls()
    return _instances[name]


def handle_inbound(name: str, request: dict,
                   config: dict | None = None) -> str:
    """全流程入口：verify → parse → 注入检查 → 返回待回复文本。"""
    ch = get_channel(name, config)
    if not ch.verify(request):
        return VERIFY_FAIL_TEXT
    msg = ch.parse(request)
    if msg is None:
        return ""
    # 平台握手类消息：不进 chat 管道、不做注入检查，直接回握手应答
    if msg.extras.get("type") == "url_verification":      # 飞书 challenge
        return json.dumps({"challenge": msg.extras.get("challenge", "")},
                          ensure_ascii=False)
    if msg.extras.get("type") == "url_verify":            # 企业微信/公众号 echostr
        return msg.text
    # 用户消息：注入检查，拦截回固定话术
    if not ch.check_injection(msg):
        return BLOCK_TEXT
    return msg.text


__all__ = ["CHANNELS", "get_channel", "handle_inbound", "BLOCK_TEXT",
           "VERIFY_FAIL_TEXT"]
