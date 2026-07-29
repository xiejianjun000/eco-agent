"""Discord 通道适配器"""

import os
import sys
import logging
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
from gateway.gateway_core import ChannelAdapter, UnifiedMessage, MessageType

logger = logging.getLogger("channel.discord")

try: import requests
except Exception: requests = None


class DiscordAdapter(ChannelAdapter):
    """Discord Bot 适配器"""

    @property
    def platform(self) -> str: return "discord"

    def __init__(self, token: str = "", gateway=None):
        self._token = token or os.environ.get("DISCORD_BOT_TOKEN", "")
        self._gateway = gateway
        self._running = False

    def is_configured(self) -> bool: return bool(self._token)

    def send_message(self, channel_id: str, message: str, reply_to: str = "") -> bool:
        if not self.is_configured() or not requests: return False
        try:
            url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
            h = {"Authorization": f"Bot {self._token}", "Content-Type": "application/json"}
            d = {"content": message}
            if reply_to: d["message_reference"] = {"message_id": reply_to}
            r = requests.post(url, headers=h, json=d, timeout=10)
            return r.status_code == 200
        except Exception as e: logger.warning(f"Discord 发送失败: {e}"); return False

    def send_card(self, channel_id: str, title: str, content: str, actions: list[dict] = None) -> bool:
        embed = {"title": title, "description": content, "color": 0x00ff00}
        if actions:
            embed["fields"] = [{"name": a.get("name",""), "value": a.get("value",""), "inline": True} for a in actions[:5]]
        return self.send_message(channel_id, f"**{title}**\n\n{content}")

    def parse_webhook(self, raw_data: dict) -> UnifiedMessage | None:
        try:
            d = raw_data.get("d", {})
            content = d.get("content", "")
            if not content: return None
            return UnifiedMessage(platform="discord", channel_id=str(d.get("channel_id","")),
                    user_id=str(d.get("author",{}).get("id","")), user_name=d.get("author",{}).get("username",""),
                    content=content, msg_type=MessageType.TEXT, raw=raw_data)
        except Exception: return None


if __name__ == "__main__":
    bot = DiscordAdapter()
    print(f"[Discord] 已配置: {bot.is_configured()}")
