"""钉钉渠道适配器。

- 机器人 webhook 加签：timestamp + "\n" + secret → HMAC-SHA256 → base64 → urlencode
  回调请求头：timestamp / sign
- outgoing 回调解析：JSON {"msgtype":"text","text":{"content":...},"senderId":...}
- 主动回复：outgoing 机器人的 sessionWebhook 或自定义机器人 webhook（带加签）
- 出站扩展：机器人单聊/群消息/卡片（api.dingtalk.com，机器人 accessToken）、
  审批实例查询（oapi topapi，旧版 access_token）——双 token 体系，均带缓存
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import urllib.parse

from .base import Channel, InboundMessage, body_json, http_get_json, http_post_json

WEBHOOK_URL = "https://oapi.dingtalk.com/robot/send?access_token={token}"
GETTOKEN_URL = "https://oapi.dingtalk.com/gettoken?appkey={key}&appsecret={secret}"
ROBOT_TOKEN_URL = "https://api.dingtalk.com/v1.0/oauth2/accessToken"
ROBOT_OTO_URL = "https://api.dingtalk.com/v1.0/robot/oToMessages/batchSend"
ROBOT_GROUP_URL = "https://api.dingtalk.com/v1.0/robot/groupMessages/send"
APPROVAL_URL = "https://oapi.dingtalk.com/topapi/processinstance/get?access_token={token}"


def sign(secret: str, timestamp: str) -> str:
    """钉钉加签算法。"""
    string_to_sign = f"{timestamp}\n{secret}"
    digest = hmac.new(secret.encode("utf-8"), string_to_sign.encode("utf-8"), hashlib.sha256).digest()
    return urllib.parse.quote_plus(base64.b64encode(digest))


class DingTalkChannel(Channel):
    name = "dingtalk"
    env_keys = ("DINGTALK_SECRET", "DINGTALK_ACCESS_TOKEN", "DINGTALK_APP_KEY", "DINGTALK_APP_SECRET", "DINGTALK_ROBOT_CODE")

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        #: 双 token 缓存 (token, 过期时间戳)：oapi access_token / 机器人 accessToken
        self._app_token_cache: tuple[str, float] = ("", 0.0)
        self._robot_token_cache: tuple[str, float] = ("", 0.0)

    def _secret(self) -> str:
        return self.config.get("secret") or os.environ.get("DINGTALK_SECRET", "")

    def _app_credentials(self) -> tuple[str, str]:
        key = self.config.get("app_key") or os.environ.get("DINGTALK_APP_KEY", "")
        secret = self.config.get("app_secret") or os.environ.get("DINGTALK_APP_SECRET", "")
        return key, secret

    def _robot_code(self) -> str:
        return self.config.get("robot_code") or os.environ.get("DINGTALK_ROBOT_CODE", "")

    def get_app_token(self) -> str:
        """旧版 oapi access_token（topapi 审批等接口用），带缓存。"""
        token, expires_at = self._app_token_cache
        if token and time.time() < expires_at - 60:
            return token
        key, secret = self._app_credentials()
        if not key or not secret:
            return ""
        resp = http_get_json(GETTOKEN_URL.format(key=key, secret=secret))
        token = resp.get("access_token", "")
        if token:
            self._app_token_cache = (token, time.time() + resp.get("expires_in", 7200))
        return token

    def get_robot_token(self) -> str:
        """新版机器人 accessToken（api.dingtalk.com 消息接口用），带缓存。"""
        token, expires_at = self._robot_token_cache
        if token and time.time() < expires_at - 60:
            return token
        key, secret = self._app_credentials()
        if not key or not secret:
            return ""
        resp = http_post_json(ROBOT_TOKEN_URL, {"appKey": key, "appSecret": secret})
        token = resp.get("accessToken", "")
        if token:
            self._robot_token_cache = (token, time.time() + int(resp.get("expireIn", 7200)))
        return token

    def _robot_send(self, url: str, payload: dict) -> bool:
        """机器人消息接口统一出站（x-acs-dingtalk-access-token 头鉴权）。"""
        token = self.get_robot_token()
        if not token:
            return False
        resp = http_post_json(url, payload, headers={"x-acs-dingtalk-access-token": token})
        return resp.get("errcode", 0) == 0

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

    def parse(self, request: dict) -> InboundMessage | None:
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
            extras={"session_webhook": data.get("sessionWebhook", ""), "sender_nick": data.get("senderNick", "")},
        )

    def reply(self, user_id: str, text: str, **kw) -> bool:
        """优先用 outgoing 的 sessionWebhook 回复；否则走自定义机器人 webhook（加签）。"""
        webhook = kw.get("session_webhook")
        if not webhook:
            token = self.config.get("access_token") or os.environ.get("DINGTALK_ACCESS_TOKEN", "")
            webhook = WEBHOOK_URL.format(token=token)
            secret = self._secret()
            if secret:
                ts = str(int(time.time() * 1000))
                webhook += f"&timestamp={ts}&sign={sign(secret, ts)}"
        payload = {"msgtype": "text", "text": {"content": text}}
        resp = http_post_json(webhook, payload)
        return resp.get("errcode") == 0

    def send_text(self, user_id: str, text: str) -> bool:
        """机器人单聊文本消息（oToMessages/batchSend，userIds 标识接收人）。"""
        payload = {
            "robotCode": self._robot_code(),
            "userIds": [user_id],
            "msgKey": "sampleText",
            "msgParam": json.dumps({"content": text}, ensure_ascii=False),
        }
        return self._robot_send(ROBOT_OTO_URL, payload)

    def send_group_message(self, group_open_id: str, text: str) -> bool:
        """机器人群消息（groupMessages/send，openConversationId 标识群）。"""
        payload = {
            "robotCode": self._robot_code(),
            "openConversationId": group_open_id,
            "msgKey": "sampleText",
            "msgParam": json.dumps({"content": text}, ensure_ascii=False),
        }
        return self._robot_send(ROBOT_GROUP_URL, payload)

    def send_card(self, user_id: str, title: str, content: str) -> bool:
        """机器人单聊卡片消息（sampleActionCard）。"""
        card = {
            "config": {"promote": False},
            "header": {"title": {"content": title, "type": "text"}, "templateId": "red"},
            "body": {"content": content, "formattedContent": f"# {title}\n\n{content}"},
        }
        payload = {
            "robotCode": self._robot_code(),
            "userIds": [user_id],
            "msgKey": "sampleActionCard",
            "msgParam": json.dumps(card, ensure_ascii=False),
        }
        return self._robot_send(ROBOT_OTO_URL, payload)

    def query_approval(self, process_instance_id: str) -> dict | None:
        """查询审批实例详情（topapi/processinstance/get，用 oapi token）。"""
        token = self.get_app_token()
        if not token:
            return None
        resp = http_post_json(APPROVAL_URL.format(token=token), {"process_instance_id": process_instance_id})
        if resp.get("errcode") == 0:
            return resp.get("process_instance", {})
        return None
