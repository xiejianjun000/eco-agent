"""Telegram 通道适配器"""

import os
import sys
import logging
import time
import threading

# 允许独立运行
if __name__ == "__main__":
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
    from gateway.gateway_core import ChannelAdapter, UnifiedMessage, MessageType
else:
    from ..gateway_core import ChannelAdapter, UnifiedMessage, MessageType

logger = logging.getLogger("channel.telegram")

try:
    import requests
except ImportError:
    requests = None


class TelegramAdapter(ChannelAdapter):
    """Telegram Bot 适配器"""

    @property
    def platform(self) -> str:
        return "telegram"

    def __init__(self, token: str = "", gateway=None):
        self._token = token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self._base_url = f"https://api.telegram.org/bot{self._token}"
        self._gateway = gateway
        self._offset = 0
        self._running = False
        self._thread: threading.Thread | None = None

    def is_configured(self) -> bool:
        return bool(self._token)

    def send_message(self, channel_id: str, message: str, reply_to: str = "") -> bool:
        if not self.is_configured():
            return False
        try:
            data = {"chat_id": channel_id, "text": message, "parse_mode": "Markdown"}
            if reply_to:
                data["reply_to_message_id"] = reply_to
            r = requests.post(f"{self._base_url}/sendMessage", json=data, timeout=10)
            return r.json().get("ok", False)
        except Exception as e:
            logger.warning(f"Telegram 发送失败: {e}")
            return False

    def send_card(self, channel_id: str, title: str, content: str,
                  actions: list[dict] = None) -> bool:
        if not self.is_configured():
            return False
        text = f"*{title}*\n\n{content}"
        return self.send_message(channel_id, text)

    def parse_webhook(self, raw_data: dict) -> UnifiedMessage | None:
        try:
            msg = raw_data.get("message", {})
            chat = msg.get("chat", {})
            text = msg.get("text", "")
            if not text:
                return None
            return UnifiedMessage(
                platform="telegram",
                channel_id=str(chat.get("id", "")),
                user_id=str(msg.get("from", {}).get("id", "")),
                user_name=msg.get("from", {}).get("first_name", ""),
                content=text,
                msg_type=MessageType.TEXT,
                raw=raw_data,
            )
        except Exception as e:
            logger.warning(f"Telegram 解析失败: {e}")
            return None

    def start_polling(self):
        """启动长轮询接收消息"""
        if not self.is_configured():
            logger.warning("Telegram 未配置，无法启动轮询")
            return
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        logger.info("[Telegram] 轮询已启动")

    def stop_polling(self):
        self._running = False

    def _poll_loop(self):
        while self._running:
            try:
                r = requests.get(f"{self._base_url}/getUpdates", params={
                    "offset": self._offset, "timeout": 30, "allowed_updates": ["message"]
                }, timeout=35)
                data = r.json()
                if data.get("ok"):
                    for update in data.get("result", []):
                        self._offset = update["update_id"] + 1
                        msg = self.parse_webhook(update)
                        if msg and self._gateway:
                            self._gateway.process_message_by_adapter(msg)
            except requests.Timeout:
                pass  # 长轮询正常超时
            except Exception as e:
                logger.warning(f"Telegram 轮询异常: {e}")
                time.sleep(5)

    def get_me(self) -> dict:
        """获取 Bot 信息"""
        if not self.is_configured():
            return {"error": "未配置"}
        r = requests.get(f"{self._base_url}/getMe", timeout=10)
        return r.json()


# ===== 独立测试 =====
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    bot = TelegramAdapter()
    if bot.is_configured():
        me = bot.get_me()
        print(f"Bot: {me}")
        bot.start_polling()
        time.sleep(5)
        bot.stop_polling()
    else:
        print("[Telegram] 未配置 TELEGRAM_BOT_TOKEN，跳过实际测试")
        print("[OK] Telegram 通道适配器代码就绪")
