#!/usr/bin/env python3
"""
wecom_bot.py — 企业微信 Bot 集成工具

提供企业微信 API 封装：消息发送、审批操作、通讯录查询。

环境变量：
  WECOM_CORP_ID / WECOM_AGENT_ID / WECOM_SECRET
  WECOM_TOKEN / WECOM_ENCODING_AES_KEY

用法：
  python -c "from gateway.platforms.wecom_bot import WecomBot; bot=WecomBot(); bot.send_text('user_id','你好')"
"""

import logging
import os
import time

try:
    import requests
except ImportError:
    requests = None

logger = logging.getLogger("wecom_bot")


class WecomBot:
    """企业微信 Bot 封装"""

    BASE_URL = "https://qyapi.weixin.qq.com/cgi-bin"

    def __init__(self):
        self.corp_id = os.environ.get("WECOM_CORP_ID", "")
        self.agent_id = os.environ.get("WECOM_AGENT_ID", "")
        self.secret = os.environ.get("WECOM_SECRET", "")
        self._token = None
        self._token_expires = 0

    def _get_token(self) -> str:
        """获取 access_token"""
        if self._token and time.time() < self._token_expires - 60:
            return self._token
        if not self.corp_id or not self.secret:
            logger.warning("企业微信未配置（WECOM_CORP_ID / WECOM_SECRET）")
            return ""
        resp = requests.get(
            f"{self.BASE_URL}/gettoken",
            params={"corpid": self.corp_id, "corpsecret": self.secret},
            timeout=10,
        )
        data = resp.json()
        if data.get("errcode") == 0:
            self._token = data["access_token"]
            self._token_expires = time.time() + data.get("expires_in", 7200)
            return self._token
        logger.error(f"企业微信 token 获取失败: {data}")
        return ""

    def _headers(self) -> dict:
        return {"Content-Type": "application/json"}

    def send_text(self, user_id: str, text: str, to_party: str = "", to_tag: str = "") -> bool:
        """发送文本消息"""
        token = self._get_token()
        if not token:
            print("[企业微信] 未配置，跳过发送")
            return False
        url = f"{self.BASE_URL}/message/send?access_token={token}"
        body = {
            "touser": user_id,
            "toparty": to_party,
            "totag": to_tag,
            "msgtype": "text",
            "agentid": int(self.agent_id) if self.agent_id else 0,
            "text": {"content": text},
            "safe": 0,
        }
        resp = requests.post(url, headers=self._headers(), json=body, timeout=10)
        result = resp.json()
        if result.get("errcode") == 0:
            logger.info(f"企业微信消息发送成功: {text[:30]}...")
            return True
        logger.error(f"企业微信消息发送失败: {result}")
        return False

    def send_text_card(self, user_id: str, title: str, description: str, url: str = "") -> bool:
        """发送文本卡片消息"""
        token = self._get_token()
        if not token:
            return False
        url_api = f"{self.BASE_URL}/message/send?access_token={token}"
        body = {
            "touser": user_id,
            "msgtype": "textcard",
            "agentid": int(self.agent_id) if self.agent_id else 0,
            "textcard": {
                "title": title,
                "description": description,
                "url": url or "https://work.weixin.qq.com",
                "btntxt": "查看详情",
            },
        }
        resp = requests.post(url_api, headers=self._headers(), json=body, timeout=10)
        result = resp.json()
        if result.get("errcode") == 0:
            return True
        logger.error(f"企业微信卡片发送失败: {result}")
        return False

    def send_news(self, user_id: str, articles: list[dict]) -> bool:
        """发送图文消息"""
        token = self._get_token()
        if not token:
            return False
        url = f"{self.BASE_URL}/message/send?access_token={token}"
        body = {
            "touser": user_id,
            "msgtype": "news",
            "agentid": int(self.agent_id) if self.agent_id else 0,
            "news": {"articles": articles},
        }
        resp = requests.post(url, headers=self._headers(), json=body, timeout=10)
        result = resp.json()
        if result.get("errcode") == 0:
            return True
        logger.error(f"企业微信图文发送失败: {result}")
        return False

    def get_user_info(self, user_id: str) -> dict | None:
        """获取成员信息"""
        token = self._get_token()
        if not token:
            return None
        url = f"{self.BASE_URL}/user/get?access_token={token}&userid={user_id}"
        resp = requests.get(url, timeout=10)
        data = resp.json()
        if data.get("errcode") == 0:
            return data
        return None

    def create_approval(self, creator_id: str, approver_id: list[str], template_id: str, details: dict) -> str | None:
        """创建审批申请

        返回审批实例 ID
        """
        token = self._get_token()
        if not token:
            return None
        url = f"{self.BASE_URL}/oa/applyevent?access_token={token}"
        body = {
            "creator_userid": creator_id,
            "template_id": template_id,
            "use_template_approver": 0,
            "approver": [{"attr": 0, "userid": approver_id}],
            "apply_data": details,
        }
        resp = requests.post(url, headers=self._headers(), json=body, timeout=10)
        data = resp.json()
        if data.get("errcode") == 0:
            return data.get("sp_no", "")
        return None

    def verify_signature(self, query: dict) -> bool:
        """验证回调 URL 签名"""
        token = os.environ.get("WECOM_TOKEN", "")
        if not token:
            return True
        signature = query.get("msg_signature", "")
        timestamp = query.get("timestamp", "")
        nonce = query.get("nonce", "")
        echostr = query.get("echostr", "")
        import hashlib

        arr = sorted([token, timestamp, nonce, echostr])
        calc_sig = hashlib.sha1("".join(arr).encode()).hexdigest()
        return calc_sig == signature


def test():
    """测试企业微信 Bot"""
    bot = WecomBot()
    print(f"Corp ID: {bot.corp_id}")
    print(f"Agent ID: {bot.agent_id}")
    if bot.corp_id and bot.secret:
        token = bot._get_token()
        print(f"Token: {'已获取' if token else '获取失败'}")
    else:
        print("未配置（需要 WECOM_CORP_ID / WECOM_AGENT_ID / WECOM_SECRET 环境变量）")


if __name__ == "__main__":
    test()
