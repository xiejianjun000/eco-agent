"""企业微信（WeCom）渠道适配器。

- 回调 URL 验证（GET echostr）+ 消息加解密：AES-256-CBC（cryptography 库，禁用 pycrypto）
  EncodingAESKey 为 43 字符，实际 key = base64(EncodingAESKey + "=")，iv = key[:16]
  明文结构：random(16) + msg_len(4, network order) + msg + receiveid
- 验签：msg_signature = sha1(sort(token, timestamp, nonce, encrypt_msg))
- 主动发消息：应用 message/send API（需 access_token）
"""
from __future__ import annotations

import base64
import hashlib
import os
import struct
import xml.etree.ElementTree as ET
from typing import Optional

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .base import (BLOCK_TEXT, Channel, InboundMessage, body_bytes, body_json,
                   http_post_json)

SEND_URL = "https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={token}"
TOKEN_URL = "https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={cid}&corpsecret={secret}"


def _sha1_sig(token: str, *parts: str) -> str:
    return hashlib.sha1("".join(sorted([token, *parts])).encode("utf-8")).hexdigest()


class WeComCrypto:
    """企业微信回调 AES 加解密（PKCS7，block=32）。"""

    def __init__(self, encoding_aes_key: str):
        if len(encoding_aes_key) != 43:
            raise ValueError("EncodingAESKey 必须为 43 字符")
        self.key = base64.b64decode(encoding_aes_key + "=")
        self.iv = self.key[:16]

    def decrypt(self, ciphertext_b64: str) -> tuple[str, str]:
        """解密 → (明文, receiveid)。"""
        raw = base64.b64decode(ciphertext_b64)
        cipher = Cipher(algorithms.AES(self.key), modes.CBC(self.iv))
        dec = cipher.decryptor()
        plain = dec.update(raw) + dec.finalize()
        pad = plain[-1]
        plain = plain[:-pad]
        msg_len = struct.unpack("!I", plain[16:20])[0]
        msg = plain[20:20 + msg_len].decode("utf-8")
        receiveid = plain[20 + msg_len:].decode("utf-8")
        return msg, receiveid

    def encrypt(self, msg: str, receiveid: str) -> str:
        plain = os.urandom(16) + struct.pack("!I", len(msg.encode("utf-8"))) \
            + msg.encode("utf-8") + receiveid.encode("utf-8")
        pad = 32 - len(plain) % 32
        plain += bytes([pad]) * pad
        cipher = Cipher(algorithms.AES(self.key), modes.CBC(self.iv))
        enc = cipher.encryptor()
        return base64.b64encode(enc.update(plain) + enc.finalize()).decode("ascii")


def _xml_get(xml_text: str, tag: str) -> str:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return ""
    el = root.find(tag)
    return el.text if el is not None and el.text else ""


class WeComChannel(Channel):
    name = "wecom"
    env_keys = ("WECOM_TOKEN", "WECOM_ENCODING_AES_KEY", "WECOM_CORP_ID",
                "WECOM_AGENT_ID", "WECOM_SECRET")

    def _token(self) -> str:
        return self.config.get("token") or os.environ.get("WECOM_TOKEN", "")

    def _crypto(self) -> WeComCrypto:
        key = self.config.get("encoding_aes_key") \
            or os.environ.get("WECOM_ENCODING_AES_KEY", "")
        return WeComCrypto(key)

    def verify(self, request: dict) -> bool:
        args = request.get("args", {})
        signature = args.get("msg_signature", "")
        timestamp = args.get("timestamp", "")
        nonce = args.get("nonce", "")
        if not signature or not timestamp or not nonce:
            return False
        if request.get("method", "POST").upper() == "GET":
            echostr = args.get("echostr", "")
            if not echostr:
                return False
            return _sha1_sig(self._token(), timestamp, nonce, echostr) == signature
        encrypt_msg = _xml_get(body_bytes(request).decode("utf-8", "ignore"), "Encrypt")
        if not encrypt_msg:
            return False
        return _sha1_sig(self._token(), timestamp, nonce, encrypt_msg) == signature

    def parse(self, request: dict) -> InboundMessage | None:
        if request.get("method", "POST").upper() == "GET":
            # 回调 URL 验证：解密 echostr
            try:
                plain, _rid = self._crypto().decrypt(request["args"]["echostr"])
            except Exception:
                return None
            return InboundMessage(channel=self.name, user_id="", text=plain,
                                  extras={"type": "url_verify"})
        xml_text = _xml_get(body_bytes(request).decode("utf-8", "ignore"), "Encrypt")
        if not xml_text:
            return None
        try:
            plain, _rid = self._crypto().decrypt(xml_text)
        except Exception:
            return None
        if _xml_get(plain, "MsgType") != "text":
            return None
        return InboundMessage(
            channel=self.name,
            user_id=_xml_get(plain, "FromUserName"),
            text=_xml_get(plain, "Content"),
            msg_id=_xml_get(plain, "MsgId"),
            extras={"agent_id": _xml_get(plain, "AgentID")},
        )

    def reply(self, user_id: str, text: str, **kw) -> bool:
        token = kw.get("access_token") or self.config.get("access_token")
        if not token:
            cid = self.config.get("corp_id") or os.environ.get("WECOM_CORP_ID", "")
            secret = self.config.get("secret") or os.environ.get("WECOM_SECRET", "")
            token = self._get_token(cid, secret).get("access_token", "")
        agent_id = self.config.get("agent_id") or os.environ.get("WECOM_AGENT_ID", "")
        payload = {"touser": user_id, "msgtype": "text",
                   "agentid": int(agent_id or 0), "text": {"content": text}}
        resp = http_post_json(SEND_URL.format(token=token), payload)
        return resp.get("errcode") == 0

    def _get_token(self, cid: str, secret: str) -> dict:
        import urllib.request
        import json as _json
        with urllib.request.urlopen(  # noqa: S310 测试中 mock
                TOKEN_URL.format(cid=cid, secret=secret), timeout=10) as r:
            return _json.loads(r.read().decode("utf-8"))


__all__ = ["WeComChannel", "WeComCrypto", "BLOCK_TEXT", "body_json"]
