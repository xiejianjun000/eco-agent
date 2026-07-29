#!/usr/bin/env python3
"""
wechat_bot.py — 微信集成工具

支持两种模式：
  1. 微信公众平台（Official Account）— 官方 API
  2. Wechaty（个人微信）— 开源方案（可选）

环境变量（模式 1）：
  WECHAT_APP_ID / WECHAT_APP_SECRET / WECHAT_TOKEN / WECHAT_ENCODING_AES_KEY

环境变量（模式 2）：
  WECHATY_PUPPET (如：wechaty-puppet-service)
  WECHATY_TOKEN (Wechaty 服务 Token)

用法：
  python -c "from gateway.platforms.wechat_bot import WechatBot; bot=WechatBot(); bot.send_template_msg('open_id','消息内容')"
"""

import os
import json
import time
import hashlib
import logging
from typing import Optional

try:
    import requests
except ImportError:
    requests = None

logger = logging.getLogger("wechat_bot")


class WechatBot:
    """微信消息封装

    优先使用公众号 API，Wechaty 作为备选。
    """

    BASE_URL = "https://api.weixin.qq.com/cgi-bin"

    def __init__(self):
        # 公众号模式
        self.app_id = os.environ.get("WECHAT_APP_ID", "")
        self.app_secret = os.environ.get("WECHAT_APP_SECRET", "")
        self._token_cache = None
        self._token_expires = 0

        # Wechaty 模式
        self.wechaty_token = os.environ.get("WECHATY_TOKEN", "")
        self.wechaty_puppet = os.environ.get("WECHATY_PUPPET", "")

    def _get_access_token(self) -> str:
        """获取公众号 access_token"""
        if self._token_cache and time.time() < self._token_expires - 60:
            return self._token_cache
        if not self.app_id or not self.app_secret:
            return ""
        try:
            resp = requests.get(
                f"{self.BASE_URL}/token",
                params={
                    "grant_type": "client_credential",
                    "appid": self.app_id,
                    "secret": self.app_secret,
                },
                timeout=10,
            )
            data = resp.json()
            if "access_token" in data:
                self._token_cache = data["access_token"]
                self._token_expires = time.time() + data.get("expires_in", 7200)
                return self._token_cache
            logger.warning(f"微信 token 获取失败: {data}")
        except Exception as e:
            logger.warning(f"微信 token 请求异常: {e}")
        return ""

    def handle_official_account_message(self, xml_data: str) -> str:
        """处理公众号消息（XML 格式），返回回复 XML"""
        import xml.etree.ElementTree as ET
        root = ET.fromstring(xml_data)
        msg_type = root.findtext("MsgType", "")
        content = root.findtext("Content", "")
        from_user = root.findtext("FromUserName", "")
        to_user = root.findtext("ToUserName", "")
        msg_id = root.findtext("MsgId", "0")

        if msg_type == "text":
            reply = self._generate_reply(content)
        elif msg_type == "event":
            event = root.findtext("Event", "")
            if event == "subscribe":
                reply = "欢迎关注 ECO AGENT 执法助手！\n发送法规名称查询法律条文。"
            elif event == "CLICK":
                reply = "请发送法规名称或描述违法事实。"
            else:
                reply = "收到事件通知。"
        else:
            reply = "抱歉，暂不支持此类型的消息。"

        return self._build_xml_reply(from_user, to_user, reply)

    def _generate_reply(self, content: str) -> str:
        """生成回复内容"""
        content = content.strip()
        if content in ("帮助", "help", "h", "?"):
            return (
                "ECO AGENT 执法助手\n\n"
                "📖 发送法规名称检索法律条文\n"
                "⚖️ 描述违法事实获取裁量建议\n"
                "📁 发送「案例」+关键词查案例\n"
                "💡 发送「帮助」查看本说明"
            )
        elif "大气" in content or "废气" in content or "排放" in content:
            return (
                f"检索到与「{content}」相关的法规：\n\n"
                "主要法规：\n"
                "- 《生态环境法典》第二编·第二分编\n\n"
                "💡 如需详细裁量建议，请提供具体的违法事实描述。"
            )
        else:
            return (
                f"收到：{content[:80]}\n\n"
                "正在检索相关法规...\n"
                "💡 发送「帮助」查看使用说明"
            )

    def _build_xml_reply(self, from_user: str, to_user: str, content: str) -> str:
        """构建 XML 回复"""
        timestamp = str(int(time.time()))
        return (
            f"<xml>\n"
            f"<ToUserName><![CDATA[{from_user}]]></ToUserName>\n"
            f"<FromUserName><![CDATA[{to_user}]]></FromUserName>\n"
            f"<CreateTime>{timestamp}</CreateTime>\n"
            f"<MsgType><![CDATA[text]]></MsgType>\n"
            f"<Content><![CDATA[{content}]]></Content>\n"
            f"</xml>"
        )

    def send_template_msg(self, open_id: str, text: str) -> bool:
        """发送模板消息（公众号）"""
        token = self._get_access_token()
        if not token:
            print("[微信] 未配置公众号，跳过发送")
            return False
        url = f"{self.BASE_URL}/message/custom/send?access_token={token}"
        body = {
            "touser": open_id,
            "msgtype": "text",
            "text": {"content": text},
        }
        resp = requests.post(url, json=body, timeout=10)
        data = resp.json()
        if data.get("errcode") == 0:
            logger.info(f"微信消息发送成功: {text[:30]}...")
            return True
        logger.warning(f"微信消息发送失败: {data}")
        return False

    def verify_signature(self, query: dict) -> bool:
        """验证微信签名（首次接入验证）"""
        token = os.environ.get("WECHAT_TOKEN", "")
        if not token:
            return True
        signature = query.get("signature", "")
        timestamp = query.get("timestamp", "")
        nonce = query.get("nonce", "")
        arr = sorted([token, timestamp, nonce])
        calc_sig = hashlib.sha1("".join(arr).encode()).hexdigest()
        return calc_sig == signature

    # ===== Wechaty 模式 =====

    def send_wechaty_message(self, contact_id: str, text: str) -> bool:
        """通过 Wechaty 发送个人微信消息"""
        if not self.wechaty_token:
            print("[微信/Wechaty] 未配置 WECHATY_TOKEN，跳过")
            return False
        try:
            url = f"https://api.chatie.io/v0/message/send"
            headers = {
                "Authorization": f"Bearer {self.wechaty_token}",
                "Content-Type": "application/json",
            }
            body = {
                "to": contact_id,
                "type": "text",
                "text": text,
            }
            resp = requests.post(url, headers=headers, json=body, timeout=10)
            if resp.status_code == 200:
                return True
        except Exception as e:
            logger.warning(f"Wechaty 发送失败: {e}")
        return False


def test():
    """测试微信 Bot"""
    bot = WechatBot()
    print(f"公众号 App ID: {bot.app_id}")
    print(f"Wechaty Token: {'已配置' if bot.wechaty_token else '未配置'}")
    if bot.app_id:
        token = bot._get_access_token()
        print(f"Access Token: {'已获取' if token else '获取失败'}")
    else:
        print("公众号未配置（需要 WECHAT_APP_ID / WECHAT_APP_SECRET）")


if __name__ == "__main__":
    test()
