"""飞书渠道适配器。

- 事件订阅 url_verification challenge 应答
- encrypt key AES 解密：key = SHA256(encrypt_key)，AES-256-CBC，iv = key[:16]，PKCS7
  密文结构（飞书官方）：base64(AES-CBC 密文) — 见 open.feishu.cn 文档
- token 校验：body.token == verification_token（加密模式下在校验前先解密）
- tenant_access_token 获取（带缓存）与发消息（im/v1/messages）
- 出站扩展：send_card 审批交互卡片（actions 含 approve/reject 回调 value）
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from typing import Optional

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .base import Channel, InboundMessage, body_json, http_post_json

TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
SEND_URL = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id"


class FeishuCrypto:
    """飞书事件订阅 encrypt 解密。"""

    def __init__(self, encrypt_key: str):
        self.key = hashlib.sha256(encrypt_key.encode("utf-8")).digest()

    def decrypt(self, ciphertext_b64: str) -> dict:
        raw = base64.b64decode(ciphertext_b64)
        cipher = Cipher(algorithms.AES(self.key), modes.CBC(self.key[:16]))
        dec = cipher.decryptor()
        plain = dec.update(raw) + dec.finalize()
        pad = plain[-1]
        plain = plain[:-pad]
        return json.loads(plain.decode("utf-8"))


class FeishuChannel(Channel):
    name = "feishu"
    env_keys = ("FEISHU_APP_ID", "FEISHU_APP_SECRET", "FEISHU_ENCRYPT_KEY",
                "FEISHU_VERIFICATION_TOKEN")

    def _verification_token(self) -> str:
        return self.config.get("verification_token") \
            or os.environ.get("FEISHU_VERIFICATION_TOKEN", "")

    def _decrypt_body(self, request: dict) -> dict:
        """若 body 为加密格式 {"encrypt": ...}，先解密。"""
        data = body_json(request)
        if "encrypt" not in data:
            return data
        key = self.config.get("encrypt_key") or os.environ.get("FEISHU_ENCRYPT_KEY", "")
        try:
            return FeishuCrypto(key).decrypt(data["encrypt"])
        except Exception:
            return {}

    def verify(self, request: dict) -> bool:
        data = self._decrypt_body(request)
        if not data:
            return False
        token = data.get("token", "")
        expected = self._verification_token()
        return bool(expected) and token == expected

    def parse(self, request: dict) -> InboundMessage | None:
        data = self._decrypt_body(request)
        if not data:
            return None
        if data.get("type") == "url_verification":
            # challenge 应答：registry.handle_inbound 读取 extras["challenge"] 直接回包
            return InboundMessage(channel=self.name, user_id="", text="",
                                  extras={"type": "url_verification",
                                          "challenge": data.get("challenge", "")})
        header = data.get("header") or {}
        event = data.get("event") or {}
        message = event.get("message") or {}
        if message.get("message_type") != "text":
            return None
        try:
            text = json.loads(message.get("content", "{}")).get("text", "")
        except ValueError:
            return None
        if not text:
            return None
        sender = (event.get("sender") or {}).get("sender_id") or {}
        return InboundMessage(
            channel=self.name,
            user_id=sender.get("open_id", ""),
            text=text,
            msg_id=message.get("message_id", ""),
            extras={"event_id": header.get("event_id", ""),
                    "chat_id": message.get("chat_id", "")},
        )

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        #: tenant_access_token 缓存 (token, 过期时间戳)
        self._token_cache: tuple[str, float] = ("", 0.0)

    def get_tenant_access_token(self) -> str:
        """获取 tenant_access_token（带缓存，过期前 60s 刷新）。"""
        token, expires_at = self._token_cache
        if token and time.time() < expires_at - 60:
            return token
        resp = http_post_json(TOKEN_URL, {
            "app_id": self.config.get("app_id") or os.environ.get("FEISHU_APP_ID", ""),
            "app_secret": self.config.get("app_secret")
                          or os.environ.get("FEISHU_APP_SECRET", ""),
        })
        token = resp.get("tenant_access_token", "")
        if token:
            self._token_cache = (token, time.time() + resp.get("expire", 7200))
        return token

    def reply(self, user_id: str, text: str, **kw) -> bool:
        token = kw.get("tenant_access_token") or self.config.get("tenant_access_token") \
            or self.get_tenant_access_token()
        payload = {"receive_id": user_id, "msg_type": "text",
                   "content": json.dumps({"text": text}, ensure_ascii=False)}
        resp = http_post_json(SEND_URL, payload,
                              headers={"Authorization": f"Bearer {token}"})
        return resp.get("code") == 0

    def send_card(self, receive_id: str, title: str, content: str,
                  approve_callback: str = "", reject_callback: str = "",
                  id_type: str = "open_id") -> bool:
        """发送交互卡片（审批场景：可带批准/拒绝回调按钮）。"""
        card: dict = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": "red" if "审批" in title else "blue",
            },
            "elements": [{"tag": "markdown", "content": content}],
        }
        if approve_callback and reject_callback:
            card["elements"].append({
                "tag": "action",
                "actions": [
                    {"tag": "button",
                     "text": {"tag": "plain_text", "content": "✅ 批准"},
                     "type": "primary",
                     "value": {"action": "approve", "callback": approve_callback}},
                    {"tag": "button",
                     "text": {"tag": "plain_text", "content": "❌ 拒绝"},
                     "type": "danger",
                     "value": {"action": "reject", "callback": reject_callback}},
                ],
            })
        token = self.config.get("tenant_access_token") \
            or self.get_tenant_access_token()
        if not token:
            return False
        url = ("https://open.feishu.cn/open-apis/im/v1/messages"
               f"?receive_id_type={id_type}")
        payload = {"receive_id": receive_id, "msg_type": "interactive",
                   "content": json.dumps(card, ensure_ascii=False)}
        resp = http_post_json(url, payload,
                              headers={"Authorization": f"Bearer {token}"})
        return resp.get("code") == 0
