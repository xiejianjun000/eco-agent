#!/usr/bin/env python3
"""
eco_peer.py — Agent 间对等消息总线 + Bot 协作房间（对标路线 P0-1/P0-2）

对标 Hermes v0.21.0：
- hermes peer / hosted room : bot 间对等 DM，多 LinkMode，消息落 canonical Bot Chat 可回放
- Bot Mode                   : 群聊房间、@提及路由、profile/roster、3 轮上限

eco 落地方案：
- PeerRegistry : 注册 agent peer（id/name/kind/transport），类似 roster
- PeerRoom     : 协作房间（group / bot / dm 三类），members 可审计
- PeerBus      : send() 消息统一落 JSONL 账本（rooms/<room_id>.jsonl），
                 任意进程按 room 回放（对标 canonical Bot Chat 落库回放）
- BotRoom 约束 : room_type=bot 时记录 max_turns 轮次预算，超限消息仍落库但
                 meta.turn_exceeded=true，由 gateway 层据此抑制 bot 回复

设计对齐 task_control.py：JSON 持久化 + 原子写，零第三方依赖；跨进程
通过 base 目录（~/.eco/peers）定位同一实例。
"""

import json
import os
import uuid
from datetime import datetime
from pathlib import Path

DEFAULT_BASE = Path(os.environ.get("ECO_PEER_DIR", "~/.eco/peers")).expanduser()
BOT_MAX_TURNS_DEFAULT = 3  # 对标 Hermes Bot Mode 3 轮上限


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _atomic_write(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


class PeerBus:
    """对等消息总线：peers 注册 + 房间 + 消息账本。"""

    def __init__(self, base: Path | str | None = None):
        self.base = Path(base) if base else DEFAULT_BASE
        self.meta_path = self.base / "meta.json"
        self.rooms_dir = self.base / "rooms"
        self.rooms_dir.mkdir(parents=True, exist_ok=True)
        if not self.meta_path.exists():
            _atomic_write(self.meta_path, {"peers": {}, "rooms": {}, "bus_keys": {}})

    # ── 内部读写 ────────────────────────────────────────────
    def _read_meta(self) -> dict:
        return json.loads(self.meta_path.read_text(encoding="utf-8"))

    def _write_meta(self, meta: dict) -> None:
        _atomic_write(self.meta_path, meta)

    def _ledger(self, room_id: str) -> Path:
        return self.rooms_dir / f"{room_id}.jsonl"

    def _append_msg(self, room_id: str, rec: dict) -> None:
        with self._ledger(room_id).open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def _read_msgs(self, room_id: str) -> list[dict]:
        path = self._ledger(room_id)
        if not path.exists():
            return []
        out = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                out.append(json.loads(line))
        return out

    # ── Peer 注册（roster）──────────────────────────────────
    def register_peer(self, peer_id: str, name: str | None = None, kind: str = "agent", transport: str | None = None) -> dict:
        """注册/更新 peer（对标 roster/profile）。peer_id 必须非空。"""
        if not peer_id or not peer_id.strip():
            raise ValueError("peer_id is required")
        peer_id = peer_id.strip()
        meta = self._read_meta()
        p = meta["peers"].get(peer_id, {})
        p.update(
            {
                "id": peer_id,
                "name": name or p.get("name") or peer_id,
                "kind": kind,
                "transport": transport or p.get("transport"),
                "registered_at": p.get("registered_at") or _now(),
                "updated_at": _now(),
            }
        )
        meta["peers"][peer_id] = p
        self._write_meta(meta)
        return p

    def list_peers(self) -> list[dict]:
        meta = self._read_meta()
        return sorted(meta["peers"].values(), key=lambda p: p["id"])

    def get_peer(self, peer_id: str) -> dict | None:
        return self._read_meta()["peers"].get(peer_id)

    def _require_peer(self, peer_id: str) -> None:
        if self.get_peer(peer_id) is None:
            raise KeyError(f"unknown peer: {peer_id} (call register_peer first)")

    # ── 房间管理 ────────────────────────────────────────────
    def create_room(
        self,
        name: str,
        members: list[str] | None = None,
        room_type: str = "group",
        max_turns: int | None = None,
        owner: str | None = None,
    ) -> dict:
        """创建房间。room_type: group(默认多 agent) / bot(Bot Mode 群聊) / dm。

        bot 房间自动应用 BOT_MAX_TURNS_DEFAULT 轮次预算；成员需已注册。
        """
        members = list(dict.fromkeys(members or []))  # 去重保序
        for m in members:
            self._require_peer(m)
        if room_type == "dm" and len(members) < 2:
            raise ValueError("dm room requires at least 2 members")
        room_id = f"r_{uuid.uuid4().hex[:10]}"
        if room_type == "bot" and max_turns is None:
            max_turns = BOT_MAX_TURNS_DEFAULT
        room = {
            "id": room_id,
            "name": name,
            "type": room_type,
            "members": members,
            "max_turns": max_turns,
            "owner": owner,
            "created_at": _now(),
            "updated_at": _now(),
        }
        meta = self._read_meta()
        meta["rooms"][room_id] = room
        self._write_meta(meta)
        return room

    def join_room(self, room_id: str, peer_id: str) -> dict:
        self._require_peer(peer_id)
        meta = self._read_meta()
        room = meta["rooms"].get(room_id)
        if room is None:
            raise KeyError(f"unknown room: {room_id}")
        if peer_id not in room["members"]:
            room["members"].append(peer_id)
            room["updated_at"] = _now()
            self._write_meta(meta)
        return room

    # ── IM 会话映射（M1 收尾：gateway 把 IM 会话 key 绑定到 room）──
    def bind_room_key(self, bus_key: str, room_id: str) -> None:
        """绑定 IM 会话 key（如 feishu:oc_xxx）到 bus 房间。"""
        if not bus_key or not room_id:
            raise ValueError("bus_key and room_id are required")
        self._ensure_room(room_id)
        meta = self._read_meta()
        meta.setdefault("bus_keys", {})[bus_key] = room_id
        self._write_meta(meta)

    def resolve_room_key(self, bus_key: str) -> str | None:
        """按 IM 会话 key 查房间 id（未绑定返回 None）。"""
        meta = self._read_meta()
        return meta.setdefault("bus_keys", {}).get(bus_key)

    def list_room_keys(self) -> list[dict]:
        """列出全部 IM 会话映射（含房间摘要，供 gateway/API 展示）。"""
        meta = self._read_meta()
        out = []
        for key, room_id in meta.setdefault("bus_keys", {}).items():
            try:
                room = self.get_room(room_id)
            except KeyError:
                room = None
            out.append(
                {
                    "bus_key": key,
                    "room_id": room_id,
                    "room_name": room["name"] if room else None,
                    "room_type": room["type"] if room else None,
                }
            )
        return sorted(out, key=lambda k: k["bus_key"])

    def list_rooms(self) -> list[dict]:
        meta = self._read_meta()
        return sorted(meta["rooms"].values(), key=lambda r: r["created_at"])

    def get_room(self, room_id: str) -> dict | None:
        return self._read_meta()["rooms"].get(room_id)

    def _ensure_room(self, room_id: str) -> dict:
        room = self.get_room(room_id)
        if room is None:
            raise KeyError(f"unknown room: {room_id}")
        return room

    # ── 发送 / 回放 ─────────────────────────────────────────
    def send(
        self,
        room_id: str,
        from_peer: str,
        text: str,
        *,
        to_peer: str | None = None,
        kind: str | None = None,
        mentions: list[str] | None = None,
        meta: dict | None = None,
    ) -> dict:
        """向房间发送一条消息，落 JSONL 账本。

        room_type=bot 时计数轮次：bot 房间内 from_peer 为 bot 的消息计入 turn，
        超过 max_turns 后 rec.meta.turn_exceeded=true（仍落库，gateway 据此抑制）。
        """
        room = self._ensure_room(room_id)
        self._require_peer(from_peer)
        if to_peer is not None:
            self._require_peer(to_peer)
        kind = kind or ("dm" if room["type"] == "dm" else "group")
        rec = {
            "msg_id": f"m_{uuid.uuid4().hex[:10]}",
            "room_id": room_id,
            "room_type": room["type"],
            "from": from_peer,
            "to": to_peer,
            "kind": kind,
            "text": text,
            "mentions": mentions or [],
            "ts": _now(),
            "meta": dict(meta or {}),
        }
        # Bot Mode 轮次预算（对标 Hermes 3 轮上限；超限消息落库但打标）
        if room["type"] == "bot" and room.get("max_turns"):
            bot_msgs = [m for m in self._read_msgs(room_id) if m.get("kind") == "bot_reply"]
            if len(bot_msgs) >= room["max_turns"]:
                rec["meta"]["turn_exceeded"] = True
                rec["meta"]["bot_turns_used"] = len(bot_msgs)
            else:
                rec["meta"]["bot_turns_used"] = len(bot_msgs) + (1 if kind == "bot_reply" else 0)
        self._append_msg(room_id, rec)
        return rec

    def history(self, room_id: str, limit: int = 50, after_ts: str | None = None) -> list[dict]:
        """回放房间账本（最新在前）。对标 canonical Bot Chat 可回放。"""
        self._ensure_room(room_id)
        msgs = self._read_msgs(room_id)
        if after_ts:
            msgs = [m for m in msgs if m["ts"] >= after_ts]
        return list(reversed(msgs[-limit:]))

    # ── 房间卡片（供 gateway/API 展示）──────────────────────
    def room_card(self, room_id: str) -> dict:
        room = self._ensure_room(room_id)
        msgs = self._read_msgs(room_id)
        card = dict(room)
        card["message_count"] = len(msgs)
        card["last_message"] = msgs[-1] if msgs else None
        return card
