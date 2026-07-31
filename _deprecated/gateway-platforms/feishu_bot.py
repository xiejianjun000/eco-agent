#!/usr/bin/env python3
"""
feishu_bot.py — 飞书 Bot 集成工具

提供飞书 API 封装：消息发送、审批操作、事件处理。

环境变量：
  FEISHU_APP_ID / FEISHU_APP_SECRET / FEISHU_VERIFICATION_TOKEN

用法：
  python -c "from gateway.platforms.feishu_bot import FeishuBot; bot=FeishuBot(); bot.send_text('open_id','你好')"
"""

import os
import json
import time
import hashlib
import base64
import logging

try:
    import requests
except ImportError:
    requests = None

logger = logging.getLogger("feishu_bot")


class FeishuBot:
    """飞书 Bot 封装"""

    BASE_URL = "https://open.feishu.cn/open-apis"

    def __init__(self):
        self.app_id = os.environ.get("FEISHU_APP_ID", "")
        self.app_secret = os.environ.get("FEISHU_APP_SECRET", "")
        self._token = None
        self._token_expires = 0

    def _get_tenant_token(self) -> str:
        """获取 tenant_access_token"""
        if self._token and time.time() < self._token_expires - 60:
            return self._token
        if not self.app_id or not self.app_secret:
            logger.warning("飞书未配置（FEISHU_APP_ID / FEISHU_APP_SECRET）")
            return ""
        resp = requests.post(
            f"{self.BASE_URL}/auth/v3/tenant_access_token/internal",
            json={"app_id": self.app_id, "app_secret": self.app_secret},
            timeout=10,
        )
        data = resp.json()
        if data.get("code") == 0:
            self._token = data["tenant_access_token"]
            self._token_expires = time.time() + data.get("expire", 7200)
            return self._token
        logger.error(f"飞书 token 获取失败: {data}")
        return ""

    def _headers(self) -> dict:
        token = self._get_tenant_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def send_text(self, receive_id: str, text: str, id_type: str = "open_id") -> bool:
        """发送文本消息"""
        if not self._get_tenant_token():
            print("[飞书] 未配置，跳过发送")
            return False
        url = f"{self.BASE_URL}/im/v1/messages?receive_id_type={id_type}"
        body = {
            "receive_id": receive_id,
            "msg_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False),
        }
        resp = requests.post(url, headers=self._headers(), json=body, timeout=10)
        result = resp.json()
        if result.get("code") == 0:
            logger.info(f"飞书消息发送成功: {text[:30]}...")
            return True
        logger.error(f"飞书消息发送失败: {result}")
        return False

    def send_card(self, receive_id: str, title: str, content: str,
                  approve_callback: str = "", reject_callback: str = "",
                  id_type: str = "open_id") -> bool:
        """发送交互卡片消息（用于审批）"""
        if not self._get_tenant_token():
            return False
        url = f"{self.BASE_URL}/im/v1/messages?receive_id_type={id_type}"

        card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": "red" if "审批" in title else "blue",
            },
            "elements": [
                {"tag": "markdown", "content": content},
            ],
        }

        # 审批按钮
        if approve_callback and reject_callback:
            card["elements"].append({
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "✅ 批准"},
                        "type": "primary",
                        "value": {"action": "approve", "callback": approve_callback},
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "❌ 拒绝"},
                        "type": "danger",
                        "value": {"action": "reject", "callback": reject_callback},
                    },
                ],
            })

        body = {
            "receive_id": receive_id,
            "msg_type": "interactive",
            "content": json.dumps(card, ensure_ascii=False),
        }
        resp = requests.post(url, headers=self._headers(), json=body, timeout=10)
        result = resp.json()
        if result.get("code") == 0:
            return True
        logger.error(f"飞书卡片发送失败: {result}")
        return False

    def get_user_info(self, user_id: str, id_type: str = "open_id") -> dict | None:
        """获取用户信息"""
        if not self._get_tenant_token():
            return None
        url = f"{self.BASE_URL}/contact/v3/users/{user_id}?user_id_type={id_type}"
        resp = requests.get(url, headers=self._headers(), timeout=10)
        data = resp.json()
        if data.get("code") == 0:
            return data.get("data", {}).get("user", {})
        return None

    def verify_event(self, body: dict) -> bool:
        """验证飞书事件回调签名"""
        token = os.environ.get("FEISHU_VERIFICATION_TOKEN", "")
        if not token:
            logger.warning("FEISHU_VERIFICATION_TOKEN 未配置")
            return True
        challenge = body.get("challenge", "")  # noqa: F841 预留：url_verification 应答
        event_token = body.get("token", "")
        return event_token == token

    def verify_card_action(self, headers: dict, body: dict) -> bool:
        """验证飞书卡片回传签名"""
        timestamp = headers.get("X-Lark-Request-Timestamp", "")
        nonce = headers.get("X-Lark-Request-Nonce", "")
        signature = headers.get("X-Lark-Signature", "")
        secret = os.environ.get("FEISHU_APP_SECRET", "")
        if not secret:
            return True
        data = json.dumps(body, ensure_ascii=False)
        raw = timestamp + nonce + secret + data
        calc_sig = base64.b64encode(hashlib.sha256(raw.encode()).digest()).decode()
        return calc_sig == signature


def test():
    """测试飞书 Bot"""
    bot = FeishuBot()
    print(f"App ID: {bot.app_id}")
    if bot.app_id:
        print("配置就绪")
        # 测试 token 获取
        token = bot._get_tenant_token()
        print(f"Token: {'已获取' if token else '获取失败'}")
    else:
        print("未配置（需要 FEISHU_APP_ID/FEISHU_APP_SECRET 环境变量）")


if __name__ == "__main__":
    test()
