#!/usr/bin/env python3
"""
im_gateway.py — IM/网关接线层（对标路线 M1 收尾：飞书/企微消息 → BotRoom 路由）

对标 Hermes v0.21.0：gateway 会话中 @BotA/@BotB 路由、消息落 canonical Bot Chat；
eco 落地方案：
- 通道归一化：feishu(v2 事件) / wecom(群回调) / http(通用) 三 adapter → 统一 ingress
- 会话映射：IM 群/单聊 key（如 feishu:oc_xxx）→ PeerBus 房间（bind_room_key）
- @提及路由：文本 @目标 + IM mentions 字段 → agent peer id；未知目标如实返回
- 自动建房间：首次 IM 消息自动 register 人类 peer + 建 bot/group 房间（autojoin）
- Bot 回复与轮次抑制：reply() 走 kind=bot_reply 落库；房间超 max_turns 时
  deliver() 返回 bot_replies=[] + reason=bot_turn_exceeded（由 gateway 上层抑制）

说明：本模块不持有真实飞书/企微凭据，不伪造 webhook 客户端；仅做事件归一化与
总线接线。接入真实通道时，把 IM 平台事件原样 POST 到 server
POST /api/v1/gateway/{channel} 即可复用全部路由逻辑。
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

CHANNELS = ("feishu", "wecom", "http")
AT_RE = re.compile(r"@([A-Za-z0-9_\-\.]+)")
_PEER_ID_RE = re.compile(r"^[A-Za-z0-9_\-\.]+$")


def _now() -> str:
    from datetime import datetime

    return datetime.now().isoformat(timespec="seconds")


def _bus(base: Path | str | None = None):
    from agent_core.eco_peer import PeerBus

    return PeerBus(base)


def _safe_peer_id(raw: str, prefix: str = "im") -> str:
    """把 IM 平台 sender/open_id 净化为总线 peer id（字母数字_- .，超长截断）。"""
    s = (raw or "").strip()
    if s and _PEER_ID_RE.match(s):
        return s[:64]
    h = hashlib.sha1((raw or "").encode("utf-8")).hexdigest()[:10]
    return f"{prefix}_{h}"


# ── 通道归一化：不同 IM 事件 → 统一 ingress ──────────────────────────
def _norm_feishu(p: dict) -> dict:
    """飞书 v2.0 事件 im.message.receive_v1。content 为 JSON 字符串（text 消息）。"""
    ev = p.get("event", p)
    chat = ev.get("message", {}).get("chat", {})
    sender = ev.get("sender", {})
    msg = ev.get("message", {})
    chat_id = chat.get("chat_id") or msg.get("chat_id") or ""
    chat_type = chat.get("chat_type") or msg.get("chat_type") or "p2p"
    open_id = (sender.get("sender_id") or {}).get("open_id") or sender.get("open_id") or ""
    sender_name = sender.get("sender_id", {}).get("union_id") or sender.get("name") or ""
    text = ""
    content = msg.get("content") or ""
    if isinstance(content, str):
        try:
            text = (json.loads(content) or {}).get("text", "")
        except Exception:
            text = content
    elif isinstance(content, dict):
        text = content.get("text") or content.get("content") or ""
    mentions = []
    for m in msg.get("mentions", []) or []:
        mentions.append(
            {
                "name": m.get("name") or m.get("key") or "",
                "id": m.get("id") or m.get("key") or "",
            }
        )
    return {
        "channel": "feishu",
        "chat_id": chat_id,
        "chat_type": chat_type,
        "sender": open_id,
        "sender_name": sender_name,
        "text": text or "",
        "mentions": mentions,
        "title": chat.get("name") or "",
        "meta": {
            "event_type": ev.get("header", {}).get("event_type")
            if isinstance(ev.get("header"), dict)
            else p.get("header", {}).get("event_type", ""),
            "message_type": msg.get("message_type", ""),
        },
    }


def _norm_wecom(p: dict) -> dict:
    """企微群机器人/回调事件（JSON 化常见形态：FromUserName/ChatId/content）。"""
    chat_id = p.get("ChatId") or p.get("chatid") or p.get("tousername") or ""
    sender = p.get("FromUserName") or p.get("fromusername") or p.get("sender") or ""
    sender_name = p.get("FromUserName") or sender
    text = p.get("Content") or p.get("content") or p.get("text", "") or ""
    if isinstance(text, (dict, list)):
        text = json.dumps(text, ensure_ascii=False)
    mentions = []
    for m in p.get("mentions", []) or []:
        mentions.append({"name": m.get("name", ""), "id": m.get("id", "")})
    return {
        "channel": "wecom",
        "chat_id": chat_id,
        "chat_type": p.get("chat_type", "group"),
        "sender": sender,
        "sender_name": sender_name,
        "text": str(text),
        "mentions": mentions,
        "title": p.get("ChatName") or p.get("chat_name") or "",
        "meta": {"msgtype": p.get("msgtype", "text"), "event": p.get("Event", "")},
    }


def _norm_http(p: dict) -> dict:
    """通用 http 通道：调用方显式给 bus_key/room_key + sender + text。"""
    return {
        "channel": "http",
        "chat_id": p.get("room_key") or p.get("bus_key") or p.get("chat_id") or "",
        "chat_type": p.get("chat_type", "group"),
        "sender": p.get("from") or p.get("sender") or "",
        "sender_name": p.get("sender_name") or p.get("from_name") or "",
        "text": str(p.get("text", "")),
        "mentions": [{"name": m.get("name", ""), "id": m.get("id", "")} for m in (p.get("mentions", []) or [])],
        "title": p.get("title") or "",
        "meta": {"raw_kind": p.get("kind", "message")},
    }


_NORMERS = {"feishu": _norm_feishu, "wecom": _norm_wecom, "http": _norm_http}


class IMGateway:
    """IM/网关接线：IM 事件归一化 → BotRoom/PeerRoom 路由（对标 M1 收尾）。"""

    def __init__(self, bus_base: Path | str | None = None, autojoin: bool = True):
        self.bus = _bus(bus_base)
        self.autojoin = autojoin

    # ── 对外主入口 ────────────────────────────────────────────
    def deliver(self, channel: str, payload: dict, *, autojoin: bool | None = None) -> dict:
        """把一条 IM 事件消息投递进总线，返回路由结果（含 @提及与 bot 回复建议）。

        返回值：{ok, channel, room_id, room_name, message, mentions,
                 bot_replies, unknown_mentions, auto_created, error?}
        """
        channel = (channel or "").lower()
        if channel not in _NORMERS:
            return {"ok": False, "error": f"unsupported channel: {channel}（支持 {list(_NORMERS)}）"}
        ing = _NORMERS[channel](payload or {})
        if not ing["chat_id"]:
            return {
                "ok": False,
                "error": f"{channel} 事件缺少 chat/room id",
                "ingress": {k: v for k, v in ing.items() if k != "meta"},
            }
        if not ing["text"]:
            return {"ok": False, "error": "空消息不投递（忽略心跳/事件）", "channel": channel, "chat_id": ing["chat_id"]}

        bus_key = f"{channel}:{ing['chat_id']}"
        sender_peer = _safe_peer_id(ing["sender"] or ing["chat_id"], prefix=f"{channel}_u")
        bus = self.bus
        # 人类 peer 注册（roster 对齐：kind=human）
        bus.register_peer(sender_peer, name=ing["sender_name"] or sender_peer, kind="human", transport=channel)

        room_id = bus.resolve_room_key(bus_key)
        auto_created = False
        if room_id is None:
            if autojoin is None:
                autojoin = self.autojoin
            if not autojoin:
                return {"ok": False, "error": f"会话未绑定房间且 autojoin=False: {bus_key}", "bus_key": bus_key}
            agent_peers = [p["id"] for p in bus.list_peers() if p.get("kind") == "agent" and p.get("id") != sender_peer]
            if not agent_peers:
                return {
                    "ok": False,
                    "error": "无已注册 agent peer（先 eco peer register）",
                    "bus_key": bus_key,
                    "sender_peer": sender_peer,
                }
            room_type = "bot" if (ing["chat_type"] in ("group", "bot", "chat") or ing["text"].startswith("@")) else "group"
            room = bus.create_room(
                ing["title"] or f"im:{channel}:{ing['chat_id'][:24]}",
                members=[sender_peer] + agent_peers,
                room_type=room_type,
                owner=sender_peer,
            )
            room_id = room["id"]
            bus.bind_room_key(bus_key, room_id)
            auto_created = True

        # @提及解析：mentions 字段 ∪ 文本 @提及 → 匹配 agent peer id/name
        mentioned_names = [m["name"] for m in ing["mentions"] if m.get("name")]
        for tok in AT_RE.findall(ing["text"]):
            if tok not in mentioned_names:
                mentioned_names.append(tok)
        mention_ids, unknown_mentions = self._resolve_mentions(mentioned_names)

        rec = bus.send(
            room_id,
            sender_peer,
            ing["text"],
            kind="group",
            mentions=mention_ids,
            meta={
                "channel": channel,
                "source": "im_gateway",
                "raw_sender": ing["sender"],
                "chat_type": ing["chat_type"],
                **ing["meta"],
            },
        )
        room = bus.get_room(room_id)

        bot_replies = []
        if room.get("type") == "bot" and mention_ids:
            if rec["meta"].get("turn_exceeded"):
                bot_replies = []  # 轮次已超限：gateway 抑制 bot 回复（消息已落库）
            else:
                bot_replies = [{"to_peer": pid, "room_id": room_id} for pid in mention_ids]
        return {
            "ok": True,
            "channel": channel,
            "room_id": room_id,
            "room_name": room["name"],
            "room_type": room["type"],
            "message": rec,
            "mentions": mention_ids,
            "unknown_mentions": unknown_mentions,
            "bot_replies": bot_replies,
            "auto_created": auto_created,
        }

    def reply(self, room_id: str, from_peer: str, text: str, *, to_peer: str | None = None, meta: dict | None = None) -> dict:
        """Bot 回复入口：kind=bot_reply 落库（计入 Bot Mode 轮次预算）。"""
        rec = self.bus.send(
            room_id, from_peer, text, to_peer=to_peer, kind="bot_reply", meta={"source": "im_gateway", **(meta or {})}
        )
        return rec

    def session_map(self) -> list[dict]:
        """当前 IM 会话映射（bus_key → 房间），供 API/控制台展示。"""
        return self.bus.list_room_keys()

    # ── 内部：@目标解析 ────────────────────────────────────────
    def _resolve_mentions(self, names: list[str]) -> tuple[list[str], list[str]]:
        """把 @ 提及目标解析为 agent peer id；解析不了的如实返回 unknown。"""
        agents = {p["id"]: p for p in self.bus.list_peers() if p.get("kind") == "agent"}
        ids, unknown = [], []
        for name in dict.fromkeys(names):  # 去重保序
            name = (name or "").strip()
            if not name:
                continue
            hit = agents.get(name)
            if hit is None:
                # 允许用 peer 的 name 别名 @（如 @环境监测员 → eco-agent）
                hit = next((p for p in agents.values() if p.get("name") == name), None)
            if hit is not None:
                if hit["id"] not in ids:
                    ids.append(hit["id"])
            else:
                unknown.append(name)
        return ids, unknown
