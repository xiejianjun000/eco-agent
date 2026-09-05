"""eco_peer 回归测试（对标路线 P0-1/P0-2，M1 收尾配套）

覆盖：peer 注册/房间创建/bot 轮次预算/@提及落库回放/IM 会话 key 绑定。
离线：零 LLM 依赖（conftest 已 ECO_LLM_DISABLE=1 + HOME 临时隔离）。
"""

import pytest

from agent_core.eco_peer import BOT_MAX_TURNS_DEFAULT, PeerBus


@pytest.fixture
def bus(tmp_path):
    return PeerBus(tmp_path / "peers")


def test_register_and_list(bus):
    bus.register_peer("bot-a", name="环境监测员", kind="agent", transport="feishu")
    bus.register_peer("ou_user1", kind="human", transport="feishu")
    peers = {p["id"]: p for p in bus.list_peers()}
    assert peers["bot-a"]["kind"] == "agent"
    assert peers["ou_user1"]["kind"] == "human"


def test_create_room_types(bus):
    bus.register_peer("bot-a", kind="agent")
    bus.register_peer("u1", kind="human")
    g = bus.create_room("group1", members=["bot-a", "u1"])
    assert g["type"] == "group" and g["max_turns"] is None
    b = bus.create_room("bot1", members=["bot-a", "u1"], room_type="bot")
    assert b["type"] == "bot" and b["max_turns"] == BOT_MAX_TURNS_DEFAULT


def test_bot_turn_budget_and_history(bus):
    bus.register_peer("bot-a", kind="agent")
    bus.register_peer("u1", kind="human")
    room = bus.create_room("b", members=["bot-a", "u1"], room_type="bot")
    bus.send(room["id"], "u1", "@bot-a 你好", mentions=["bot-a"])
    for i in range(BOT_MAX_TURNS_DEFAULT):
        rec = bus.send(room["id"], "bot-a", f"reply{i + 1}", kind="bot_reply")
        assert not rec["meta"].get("turn_exceeded")
    over = bus.send(room["id"], "bot-a", "reply4", kind="bot_reply")
    assert over["meta"]["turn_exceeded"] is True
    hist = bus.history(room["id"])
    assert len(hist) == 1 + BOT_MAX_TURNS_DEFAULT + 1  # 全部落库可回放
    assert hist[0]["meta"]["turn_exceeded"] is True


def test_im_bus_key_binding(bus):
    bus.register_peer("bot-a", kind="agent")
    bus.register_peer("u1", kind="human")
    room = bus.create_room("生态值班群", members=["bot-a", "u1"], room_type="bot")
    bus.bind_room_key("feishu:oc_demo1", room["id"])
    assert bus.resolve_room_key("feishu:oc_demo1") == room["id"]
    assert bus.resolve_room_key("feishu:oc_other") is None
    keys = {k["bus_key"]: k["room_id"] for k in bus.list_room_keys()}
    assert keys["feishu:oc_demo1"] == room["id"]
    assert bus.room_card(room["id"])["message_count"] == 0


def test_bind_requires_existing_room(bus):
    with pytest.raises(KeyError):
        bus.bind_room_key("feishu:x", "r_nonexistent")


def test_send_requires_registered_peer(bus):
    bus.register_peer("u1", kind="human")
    room = bus.create_room("r", members=["u1"])
    with pytest.raises(KeyError):
        bus.send(room["id"], "ghost", "hi")
