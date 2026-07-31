"""钉钉渠道适配器。

- 机器人 webhook 加签：timestamp + "\n" + secret → HMAC-SHA256 → base64 → urlencode
  回调请求头：timestamp / sign
- outgoing 回调解析：JSON {"msgtype":"text","text":{"content":...},"senderId":...}
- 主动回复：outgoing 机器人的 sessionWebhook 或自定义机器人 webhook（带加签）
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
import urllib.parse
from typing import Optional

from .base import Channel, InboundMessage, body_json, http_post_json

WEBHOOK_URL = "https://oapi.dingtalk.com/robot/send?access_token={token}"


def sign(secret: str, timestamp: str) -> str:
    """钉钉加签算法。"""
    string_to_sign = f"{timestamp}\n{secret}"
    digest = hmac.new(secret.encode("utf-8"), string_to_sign.encode("utf-8"),
                      hashlib.sha256).digest()
    return urllib.parse.quote_plus(base64.b64encode(digest))


class DingTalkChannel(Channel):
    name = "dingtalk"
    env_keys = ("DINGTALK_SECRET", "DINGTALK_ACCESS_TOKEN")

    def _secret(self) -> str:
        return self.config.get("secret") or os.environ.get("DINGTALK_SECRET", "")

    def verify(self, request: dict) -> bool:
        headers = request.get("headers", {})
        timestamp = headers.get("timestamp") or request.get("args", {}).get("timestamp", "")
        sign_val = headers.get("sign") or request.get("args", {}).get("sign", "")
        if not timestamp or not sign_val:
            return False
        # 防重放：timestamp 超过 1 小时拒绝
        try:
            if abs(time.time() * 1000 - float(timestamp)) > 3600_000:
                return False
        except ValueError:
            return False
        expected = urllib.parse.unquote_plus(sign(self._secret(), str(timestamp)))
        return hmac.compare_digest(expected, urllib.parse.unquote_plus(str(sign_val)))

    def parse(self, request: dict) -> Optional[InboundMessage]:
        data = body_json(request)
        if data.get("msgtype") != "text":
            return None
        text = (data.get("text") or {}).get("content", "").strip()
        if not text:
            return None
        return InboundMessage(
            channel=self.name,
            user_id=data.get("senderId", ""),
            text=text,
            msg_id=data.get("msgId", ""),
            extras={"session_webhook": data.get("sessionWebhook", ""),
                    "sender_nick": data.get("senderNick", "")},
        )

    def reply(self, user_id: str, text: str, **kw) -> bool:
        """优先用 outgoing 的 sessionWebhook 回复；否则走自定义机器人 webhook（加签）。"""
        webhook = kw.get("session_webhook")
        if not webhook:
            token = self.config.get("access_token") \
                or os.environ.get("DINGTALK_ACCESS_TOKEN", "")
            webhook = WEBHOOK_URL.format(token=token)
            secret = self._secret()
            if secret:
                ts = str(int(time.time() * 1000))
                webhook += f"&timestamp={ts}&sign={sign(secret, ts)}"
        payload = {"msgtype": "text", "text": {"content": text}}
        resp = http_post_json(webhook, payload)
        return resp.get("errcode") == 0
