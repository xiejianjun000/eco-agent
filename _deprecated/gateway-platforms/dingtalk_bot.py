#!/usr/bin/env python3
"""
dingtalk_bot.py — 钉钉 Bot 集成工具

提供钉钉 API 封装：消息发送、审批操作、机器人回调。

环境变量：
  DINGTALK_APP_KEY / DINGTALK_APP_SECRET / DINGTALK_ROBOT_CODE

用法：
  python -c "from gateway.platforms.dingtalk_bot import DingTalkBot; bot=DingTalkBot(); bot.send_text('user_id','你好')"
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import time

try:
    import requests
except ImportError:
    requests = None

logger = logging.getLogger("dingtalk_bot")


class DingTalkBot:
    """钉钉 Bot 封装"""

    BASE_URL = "https://oapi.dingtalk.com"
    API_URL = "https://api.dingtalk.com"

    def __init__(self):
        self.app_key = os.environ.get("DINGTALK_APP_KEY", "")
        self.app_secret = os.environ.get("DINGTALK_APP_SECRET", "")
        self.robot_code = os.environ.get("DINGTALK_ROBOT_CODE", "")
        self._token = None
        self._token_expires = 0

    def _get_token(self) -> str:
        """获取 access_token"""
        if self._token and time.time() < self._token_expires - 60:
            return self._token
        if not self.app_key or not self.app_secret:
            logger.warning("钉钉未配置（DINGTALK_APP_KEY / DINGTALK_APP_SECRET）")
            return ""
        resp = requests.post(
            f"{self.BASE_URL}/gettoken",
            params={"appkey": self.app_key, "appsecret": self.app_secret},
            timeout=10,
        )
        data = resp.json()
        if data.get("errcode") == 0:
            self._token = data["access_token"]
            self._token_expires = time.time() + data.get("expires_in", 7200)
            return self._token
        logger.error(f"钉钉 token 获取失败: {data}")
        return ""

    def _get_robot_token(self) -> str:
        """获取机器人 access_token"""
        if not self.app_key or not self.app_secret:
            return ""
        resp = requests.post(
            f"{self.API_URL}/v1.0/oauth2/accessToken",
            json={"appKey": self.app_key, "appSecret": self.app_secret},
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        data = resp.json()
        if "accessToken" in data:
            return data["accessToken"]
        return ""

    def send_text(self, user_id: str, text: str) -> bool:
        """发送文本消息到单聊"""
        token = self._get_robot_token()
        if not token:
            print("[钉钉] 未配置，跳过发送")
            return False
        url = f"{self.API_URL}/v1.0/robot/oToMessages/batchSend"
        headers = {
            "x-acs-dingtalk-access-token": token,
            "Content-Type": "application/json",
        }
        body = {
            "robotCode": self.robot_code,
            "userIds": [user_id],
            "msgKey": "sampleText",
            "msgParam": json.dumps({"content": text}, ensure_ascii=False),
        }
        resp = requests.post(url, headers=headers, json=body, timeout=10)
        if resp.status_code == 200:
            logger.info(f"钉钉消息发送成功: {text[:30]}...")
            return True
        logger.error(f"钉钉消息发送失败: {resp.status_code} {resp.text}")
        return False

    def send_group_message(self, group_open_id: str, text: str) -> bool:
        """发送群消息"""
        token = self._get_robot_token()
        if not token:
            return False
        url = f"{self.API_URL}/v1.0/robot/groupMessages/send"
        headers = {
            "x-acs-dingtalk-access-token": token,
            "Content-Type": "application/json",
        }
        body = {
            "robotCode": self.robot_code,
            "openConversationId": group_open_id,
            "msgKey": "sampleText",
            "msgParam": json.dumps({"content": text}, ensure_ascii=False),
        }
        resp = requests.post(url, headers=headers, json=body, timeout=10)
        if resp.status_code == 200:
            return True
        logger.error(f"钉钉群消息发送失败: {resp.text}")
        return False

    def send_card(self, user_id: str, title: str, content: str) -> bool:
        """发送卡片消息"""
        token = self._get_robot_token()
        if not token:
            return False
        url = f"{self.API_URL}/v1.0/robot/oToMessages/batchSend"
        headers = {
            "x-acs-dingtalk-access-token": token,
            "Content-Type": "application/json",
        }
        card = {
            "config": {"promote": False},
            "header": {
                "title": {"content": title, "type": "text"},
                "templateId": "red",
            },
            "body": {
                "content": content,
                "formattedContent": f"# {title}\n\n{content}",
            },
        }
        body = {
            "robotCode": self.robot_code,
            "userIds": [user_id],
            "msgKey": "sampleActionCard",
            "msgParam": json.dumps(card, ensure_ascii=False),
        }
        resp = requests.post(url, headers=headers, json=body, timeout=10)
        if resp.status_code == 200:
            return True
        logger.error(f"钉钉卡片发送失败: {resp.text}")
        return False

    def query_approval(self, process_instance_id: str) -> dict | None:
        """查询审批实例"""
        token = self._get_token()
        if not token:
            return None
        url = f"{self.BASE_URL}/topapi/processinstance/get?access_token={token}"
        resp = requests.post(
            url,
            json={"process_instance_id": process_instance_id},
            timeout=10,
        )
        data = resp.json()
        if data.get("errcode") == 0:
            return data.get("process_instance", {})
        return None

    def verify_signature(self, timestamp: str, sign: str) -> bool:
        """验证钉钉回调签名"""
        secret = self.app_secret
        if not secret or not timestamp or not sign:
            return True
        string_to_sign = f"{timestamp}\n{secret}"
        hmac_code = hmac.new(secret.encode(), string_to_sign.encode(), hashlib.sha256).digest()
        calc_sign = base64.b64encode(hmac_code).decode()
        return calc_sign == sign


def test():
    """测试钉钉 Bot"""
    bot = DingTalkBot()
    print(f"App Key: {bot.app_key[:10] if bot.app_key else '未配置'}...")
    print(f"Robot Code: {bot.robot_code[:10] if bot.robot_code else '未配置'}...")
    if bot.app_key and bot.app_secret:
        token = bot._get_token()
        print(f"Token: {'已获取' if token else '获取失败'}")
    else:
        print("未配置（需要 DINGTALK_APP_KEY / DINGTALK_APP_SECRET 环境变量）")


if __name__ == "__main__":
    test()
