"""im_gateway 接线测试（对标路线 M1 收尾：飞书/企微消息 → BotRoom 路由）

覆盖：feishu/wecom/http 三通道归一化、@提及路由、自动建房间、
bot 回复轮次预算抑制、会话 key 映射。离线零 LLM。
"""

import json

import pytest

from agent_core.im_gateway import IMGateway


@pytest.fixture
def gw(tmp_path):
    g = IMGateway(tmp_path / "peers")
    g.bus.register_peer("bot-a", name="环境监测员", kind="agent", transport="feishu")
    g.bus.register_peer("bot-b", name="污染预警", kind="agent", transport="wecom")
    return g


def _feishu(chat_id="oc_demo1", text="@bot-a hi", sender="ou_user1"):
    return {
        "schema": "2.0",
        "header": {"event_type": "im.message.receive_v1"},
        "event": {
            "message": {
                "chat_id": chat_id,
                "chat_type": "group",
                "message_type": "text",
                "content": json.dumps({"text": text}, ensure_ascii=False),
            },
            "sender": {"sender_id": {"open_id": sender}},
        },
    }


def test_feishu_autojoin_and_mention(gw):
    r = gw.deliver("feishu", _feishu())
    assert r["ok"] and r["auto_created"] and r["room_type"] == "bot"
    assert r["mentions"] == ["bot-a"]
    assert [x["to_peer"] for x in r["bot_replies"]] == ["bot-a"]
    # 同会话第二次投递复用同一房间
    r2 = gw.deliver("feishu", _feishu(text="@bot-b @bot-a 一起看"))
    assert r2["room_id"] == r["room_id"] and not r2["auto_created"]
    assert r2["mentions"] == ["bot-b", "bot-a"]


def test_wecom_channel(gw):
    r = gw.deliver("wecom", {"ChatId": "wr_w1", "FromUserName": "wm_user1", "Content": "@bot-a 今天AQI多少", "msgtype": "text"})
    assert r["ok"] and r["room_type"] == "bot"
    assert r["mentions"] == ["bot-a"]
    assert gw.bus.resolve_room_key("wecom:wr_w1") == r["room_id"]


def test_http_channel_no_mention_plain_group(gw):
    r = gw.deliver("http", {"room_key": "svc_room1", "from": "svc_x", "text": "日常同步数据正常"})
    assert r["ok"] and r["mentions"] == [] and r["bot_replies"] == []
    assert r["room_type"] in ("bot", "group")


def test_turn_budget_suppression(gw):
    r = gw.deliver("feishu", _feishu())
    room = r["room_id"]
    for i in range(3):
        gw.reply(room, "bot-a", f"r{i + 1}")
    r2 = gw.deliver("feishu", _feishu(text="@bot-a 还能回吗"))
    assert r2["ok"]
    assert r2["message"]["meta"]["turn_exceeded"] is True
    assert r2["bot_replies"] == []  # gateway 抑制


def test_unknown_mention_reported_honestly(gw):
    r = gw.deliver("feishu", _feishu(text="@ghost-bot hi"))
    assert r["ok"] and r["mentions"] == []
    assert r["unknown_mentions"] == ["ghost-bot"]
    assert r["bot_replies"] == []


def test_empty_text_not_delivered(gw):
    r = gw.deliver("feishu", _feishu(text=""))
    assert not r["ok"] and "空消息" in r["error"]


def test_unsupported_channel(gw):
    r = gw.deliver("telegram", {"text": "x"})
    assert not r["ok"]


def test_no_agent_peer_fails_autojoin(tmp_path):
    g = IMGateway(tmp_path / "peers2")  # 无任何 agent peer
    r = g.deliver("feishu", _feishu())
    assert not r["ok"] and "无已注册 agent peer" in r["error"]
