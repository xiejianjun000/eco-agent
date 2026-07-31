"""飞书渠道适配器。

- 事件订阅 url_verification challenge 应答
- encrypt key AES 解密：key = SHA256(encrypt_key)，AES-256-CBC，iv = key[:16]，PKCS7
  密文结构（飞书官方）：base64(AES-CBC 密文) — 见 open.feishu.cn 文档
- token 校验：body.token == verification_token（加密模式下在校验前先解密）
- tenant_access_token 获取与发消息（im/v1/messages）
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
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

    def get_tenant_access_token(self) -> str:
        resp = http_post_json(TOKEN_URL, {
            "app_id": self.config.get("app_id") or os.environ.get("FEISHU_APP_ID", ""),
            "app_secret": self.config.get("app_secret")
                          or os.environ.get("FEISHU_APP_SECRET", ""),
        })
        return resp.get("tenant_access_token", "")

    def reply(self, user_id: str, text: str, **kw) -> bool:
        token = kw.get("tenant_access_token") or self.config.get("tenant_access_token") \
            or self.get_tenant_access_token()
        payload = {"receive_id": user_id, "msg_type": "text",
                   "content": json.dumps({"text": text}, ensure_ascii=False)}
        resp = http_post_json(SEND_URL, payload,
                              headers={"Authorization": f"Bearer {token}"})
        return resp.get("code") == 0
