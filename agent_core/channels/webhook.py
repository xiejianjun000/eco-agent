"""通用自定义 webhook 渠道适配器。

- HMAC-SHA256 共享密钥验签：header X-Signature = "sha256=" + hex(hmac(secret, body))
- 协议：JSON {"user_id": ..., "text": ...} 进，{"reply": ...} 出
- 可选 response_url：reply 时回推结果
"""
from __future__ import annotations

import hashlib
import hmac
import os
from typing import Optional

from .base import Channel, InboundMessage, body_bytes, body_json, http_post_json


def sign_body(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode("utf-8"), body,
                                hashlib.sha256).hexdigest()


class WebhookChannel(Channel):
    name = "webhook"
    env_keys = ("WEBHOOK_SECRET",)

    def _secret(self) -> str:
        return self.config.get("secret") or os.environ.get("WEBHOOK_SECRET", "")

    def verify(self, request: dict) -> bool:
        headers = request.get("headers", {})
        sig = headers.get("X-Signature", "")
        secret = self._secret()
        if not sig or not secret:
            return False
        expected = sign_body(secret, body_bytes(request))
        return hmac.compare_digest(expected, sig)

    def parse(self, request: dict) -> Optional[InboundMessage]:
        data = body_json(request)
        user_id = data.get("user_id", "")
        text = (data.get("text") or "").strip()
        if not user_id or not text:
            return None
        return InboundMessage(channel=self.name, user_id=str(user_id), text=text,
                              msg_id=str(data.get("msg_id", "")),
                              extras={"response_url": data.get("response_url", "")})

    def reply(self, user_id: str, text: str, **kw) -> bool:
        response_url = kw.get("response_url") or self.config.get("response_url", "")
        if not response_url:
            # 无回推地址：gateway HTTP 层直接以 {"reply": text} 同步回包即可
            return True
        secret = self._secret()
        import json as _json
        body = _json.dumps({"user_id": user_id, "reply": text},
                           ensure_ascii=False).encode("utf-8")
        headers = {"X-Signature": sign_body(secret, body)} if secret else {}
        import urllib.request
        req = urllib.request.Request(response_url, data=body, method="POST")
        req.add_header("Content-Type", "application/json; charset=utf-8")
        for k, v in headers.items():
            req.add_header(k, v)
        with urllib.request.urlopen(req, timeout=10) as r:  # noqa: S310 测试中 mock
            return 200 <= r.status < 300
