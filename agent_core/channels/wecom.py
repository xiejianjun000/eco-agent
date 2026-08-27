"""企业微信（WeCom）渠道适配器。

- 回调 URL 验证（GET echostr）+ 消息加解密：AES-256-CBC（cryptography 库，禁用 pycrypto）
  EncodingAESKey 为 43 字符，实际 key = base64(EncodingAESKey + "=")，iv = key[:16]
  明文结构：random(16) + msg_len(4, network order) + msg + receiveid
- 验签：msg_signature = sha1(sort(token, timestamp, nonce, encrypt_msg))
- 主动发消息：应用 message/send API（需 access_token，带缓存）
- 出站扩展：文本卡片 / 图文消息 / OA 审批申请（oa/applyevent）
"""
from __future__ import annotations

import base64
import hashlib
import os
import struct
import time
import xml.etree.ElementTree as ET
from typing import Optional

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .base import (BLOCK_TEXT, Channel, InboundMessage, body_bytes, body_json,
                   http_get_json, http_post_json)

SEND_URL = "https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={token}"
TOKEN_URL = "https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={cid}&corpsecret={secret}"
APPROVAL_URL = "https://qyapi.weixin.qq.com/cgi-bin/oa/applyevent?access_token={token}"


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

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        #: access_token 缓存 (token, 过期时间戳)
        self._token_cache: tuple[str, float] = ("", 0.0)

    def _agent_id(self) -> int:
        agent_id = self.config.get("agent_id") or os.environ.get("WECOM_AGENT_ID", "")
        return int(agent_id or 0)

    def get_access_token(self) -> str:
        """应用 access_token（带缓存，过期前 60s 刷新）。"""
        token = self.config.get("access_token")
        if token:
            return token
        token, expires_at = self._token_cache
        if token and time.time() < expires_at - 60:
            return token
        cid = self.config.get("corp_id") or os.environ.get("WECOM_CORP_ID", "")
        secret = self.config.get("secret") or os.environ.get("WECOM_SECRET", "")
        resp = self._get_token(cid, secret)
        token = resp.get("access_token", "")
        if token:
            self._token_cache = (token, time.time() + resp.get("expires_in", 7200))
        return token

    def reply(self, user_id: str, text: str, **kw) -> bool:
        token = kw.get("access_token") or self.get_access_token()
        payload = {"touser": user_id, "msgtype": "text",
                   "agentid": self._agent_id(), "text": {"content": text}}
        resp = http_post_json(SEND_URL.format(token=token), payload)
        return resp.get("errcode") == 0

    def send_text_card(self, user_id: str, title: str, description: str,
                       url: str = "") -> bool:
        """发送文本卡片消息。"""
        token = self.get_access_token()
        if not token:
            return False
        payload = {"touser": user_id, "msgtype": "textcard",
                   "agentid": self._agent_id(),
                   "textcard": {"title": title, "description": description,
                                "url": url or "https://work.weixin.qq.com",
                                "btntxt": "查看详情"}}
        resp = http_post_json(SEND_URL.format(token=token), payload)
        return resp.get("errcode") == 0

    def send_news(self, user_id: str, articles: list[dict]) -> bool:
        """发送图文消息。"""
        token = self.get_access_token()
        if not token:
            return False
        payload = {"touser": user_id, "msgtype": "news",
                   "agentid": self._agent_id(),
                   "news": {"articles": articles}}
        resp = http_post_json(SEND_URL.format(token=token), payload)
        return resp.get("errcode") == 0

    def create_approval(self, creator_id: str, approver_id: list[str],
                        template_id: str, details: dict) -> str | None:
        """创建 OA 审批申请，成功返回审批实例 ID（sp_no）。"""
        token = self.get_access_token()
        if not token:
            return None
        payload = {"creator_userid": creator_id,
                   "template_id": template_id,
                   "use_template_approver": 0,
                   "approver": [{"attr": 0, "userid": approver_id}],
                   "apply_data": details}
        resp = http_post_json(APPROVAL_URL.format(token=token), payload)
        if resp.get("errcode") == 0:
            return resp.get("sp_no", "")
        return None

    def _get_token(self, cid: str, secret: str) -> dict:
        return http_get_json(TOKEN_URL.format(cid=cid, secret=secret))


__all__ = ["WeComChannel", "WeComCrypto", "BLOCK_TEXT", "body_json"]
