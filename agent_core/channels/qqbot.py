"""QQ 频道机器人渠道适配器。

- ED25519 验签（cryptography 库）：
  signature = Ed25519.sign(seed 派生私钥, timestamp + body)，hex 编码
  请求头：X-Signature-Ed25519 / X-Signature-Timestamp
  官方要求用 bot secret 重复补至 32 字节作为私钥 seed
- webhook 回调解析：{"op":0,"d":{"content":...,"author":{"id":...}}}
- 主动发消息：POST /channels/{channel_id}/messages
"""
from __future__ import annotations

import os
from typing import Optional

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey)
from cryptography.exceptions import InvalidSignature

from .base import Channel, InboundMessage, body_bytes, body_json, http_post_json

SEND_URL = "https://api.sgroup.qq.com/channels/{channel_id}/messages"


def _seed_from_secret(secret: str) -> bytes:
    """官方规则：secret 重复拼接直至 ≥32 字节，取前 32 字节为 seed。"""
    while len(secret.encode("utf-8")) < 32:
        secret += secret
    return secret.encode("utf-8")[:32]


class QQBotChannel(Channel):
    name = "qqbot"
    env_keys = ("QQBOT_APP_ID", "QQBOT_SECRET", "QQBOT_TOKEN")

    def _secret(self) -> str:
        return self.config.get("secret") or os.environ.get("QQBOT_SECRET", "")

    def verify(self, request: dict) -> bool:
        headers = request.get("headers", {})
        sig_hex = headers.get("X-Signature-Ed25519", "")
        timestamp = headers.get("X-Signature-Timestamp", "")
        if not sig_hex or not timestamp:
            return False
        secret = self._secret()
        if not secret:
            return False
        try:
            private_key = Ed25519PrivateKey.from_private_bytes(_seed_from_secret(secret))
            public_key: Ed25519PublicKey = private_key.public_key()
            public_key.verify(bytes.fromhex(sig_hex),
                              timestamp.encode("utf-8") + body_bytes(request))
            return True
        except (InvalidSignature, ValueError):
            return False

    def parse(self, request: dict) -> InboundMessage | None:
        data = body_json(request)
        # op=11 心跳回调等控制帧忽略；只处理 op=0 消息事件
        if data.get("op") != 0:
            return None
        d = data.get("d") or {}
        content = (d.get("content") or "").strip()
        if not content:
            return None
        author = d.get("author") or {}
        return InboundMessage(
            channel=self.name,
            user_id=author.get("id", ""),
            text=content,
            msg_id=d.get("id", ""),
            extras={"channel_id": d.get("channel_id", ""),
                    "guild_id": d.get("guild_id", "")},
        )

    def reply(self, user_id: str, text: str, **kw) -> bool:
        channel_id = kw.get("channel_id") or self.config.get("channel_id", "")
        token = self.config.get("token") or os.environ.get("QQBOT_TOKEN", "")
        app_id = self.config.get("app_id") or os.environ.get("QQBOT_APP_ID", "")
        payload = {"content": text}
        if kw.get("msg_id"):
            payload["msg_id"] = kw["msg_id"]
        resp = http_post_json(
            SEND_URL.format(channel_id=channel_id), payload,
            headers={"Authorization": f"QQBot {token}" if not app_id
                     else f"Bot {app_id}.{token}"})
        return "id" in resp or resp.get("code") == 0
