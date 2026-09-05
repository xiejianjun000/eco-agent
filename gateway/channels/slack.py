"""Slack 通道适配器"""

import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
from gateway.gateway_core import ChannelAdapter, MessageType, UnifiedMessage

logger = logging.getLogger("channel.slack")
try:
    import requests
except Exception:
    requests = None


class SlackAdapter(ChannelAdapter):
    @property
    def platform(self) -> str:
        return "slack"

    def __init__(self, token: str = "", signing_secret: str = ""):
        self._token = token or os.environ.get("SLACK_BOT_TOKEN", "")
        self._signing_secret = signing_secret or os.environ.get("SLACK_SIGNING_SECRET", "")

    def is_configured(self) -> bool:
        return bool(self._token)

    def send_message(self, channel_id: str, message: str, reply_to: str = "") -> bool:
        if not self.is_configured() or not requests:
            return False
        try:
            r = requests.post(
                "https://slack.com/api/chat.postMessage",
                headers={"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"},
                json={"channel": channel_id, "text": message, "thread_ts": reply_to if reply_to else None},
                timeout=10,
            )
            return r.json().get("ok", False)
        except Exception as e:
            logger.warning(f"Slack 发送失败: {e}")
            return False

    def send_card(self, channel_id: str, title: str, content: str, actions: list[dict] = None) -> bool:
        blocks = [
            {"type": "header", "text": {"type": "plain_text", "text": title}},
            {"type": "section", "text": {"type": "mrkdwn", "text": content[:2000]}},
        ]
        if actions:
            blocks.append(
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": a.get("name", "")},
                            "value": a.get("value", ""),
                        }
                        for a in actions[:5]
                    ],
                }
            )
        r = requests.post(
            "https://slack.com/api/chat.postMessage",
            headers={"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"},
            json={"channel": channel_id, "blocks": blocks},
            timeout=10,
        )
        return r.json().get("ok", False)

    def parse_webhook(self, raw_data: dict) -> UnifiedMessage | None:
        try:
            event = raw_data.get("event", {})
            text = event.get("text", "")
            if not text:
                return None
            return UnifiedMessage(
                platform="slack",
                channel_id=event.get("channel", ""),
                user_id=event.get("user", ""),
                content=text,
                msg_type=MessageType.TEXT,
                raw=raw_data,
            )
        except Exception:
            return None


if __name__ == "__main__":
    bot = SlackAdapter()
    print(f"[Slack] 已配置: {bot.is_configured()}")
