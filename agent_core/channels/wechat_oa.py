"""微信公众号（服务号/订阅号）渠道适配器。

- signature 校验：sha1(sort(token, timestamp, nonce))
- XML 消息解析（文本消息）
- 客服消息接口主动发消息（需 access_token）
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.request
import xml.etree.ElementTree as ET
from typing import Optional

from .base import Channel, InboundMessage, body_bytes, http_post_json

KEFU_URL = "https://api.weixin.qq.com/cgi-bin/message/custom/send?access_token={token}"
TOKEN_URL = ("https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential"
             "&appid={appid}&secret={secret}")


def check_signature(token: str, timestamp: str, nonce: str, signature: str) -> bool:
    if not all([token, timestamp, nonce, signature]):
        return False
    digest = hashlib.sha1(
        "".join(sorted([token, timestamp, nonce])).encode("utf-8")).hexdigest()
    return digest == signature


def _xml_get(xml_text: str, tag: str) -> str:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return ""
    el = root.find(tag)
    return el.text if el is not None and el.text else ""


class WeChatOAChannel(Channel):
    name = "wechat_oa"
    env_keys = ("WECHAT_OA_TOKEN", "WECHAT_OA_APP_ID", "WECHAT_OA_APP_SECRET")

    def _token(self) -> str:
        return self.config.get("token") or os.environ.get("WECHAT_OA_TOKEN", "")

    def verify(self, request: dict) -> bool:
        args = request.get("args", {})
        return check_signature(self._token(), args.get("timestamp", ""),
                               args.get("nonce", ""), args.get("signature", ""))

    def parse(self, request: dict) -> Optional[InboundMessage]:
        if request.get("method", "POST").upper() == "GET":
            # 服务器配置 URL 验证：回显 echostr
            echostr = request.get("args", {}).get("echostr", "")
            return InboundMessage(channel=self.name, user_id="", text=echostr,
                                  extras={"type": "url_verify"}) if echostr else None
        xml_text = body_bytes(request).decode("utf-8", "ignore")
        if _xml_get(xml_text, "MsgType") != "text":
            return None
        return InboundMessage(
            channel=self.name,
            user_id=_xml_get(xml_text, "FromUserName"),
            text=_xml_get(xml_text, "Content"),
            msg_id=_xml_get(xml_text, "MsgId"),
            extras={"to_user": _xml_get(xml_text, "ToUserName")},
        )

    def reply(self, user_id: str, text: str, **kw) -> bool:
        token = kw.get("access_token") or self.config.get("access_token")
        if not token:
            appid = self.config.get("app_id") or os.environ.get("WECHAT_OA_APP_ID", "")
            secret = self.config.get("app_secret") \
                or os.environ.get("WECHAT_OA_APP_SECRET", "")
            with urllib.request.urlopen(  # noqa: S310 测试中 mock
                    TOKEN_URL.format(appid=appid, secret=secret), timeout=10) as r:
                token = json.loads(r.read().decode("utf-8")).get("access_token", "")
        payload = {"touser": user_id, "msgtype": "text", "text": {"content": text}}
        resp = http_post_json(KEFU_URL.format(token=token), payload)
        return resp.get("errcode") == 0
