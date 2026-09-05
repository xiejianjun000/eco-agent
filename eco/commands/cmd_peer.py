"""
eco peer - Agent 对等消息总线 + Bot 协作房间（对标路线 P0-1/P0-2）

对标 Hermes：
  eco peer register <id> [--name N] [--kind agent|human]     # roster
  eco peer rooms                                             # 房间列表
  eco peer create <name> --member a --member b [--type bot|group|dm] [--owner o]
  eco peer send <room_id> --from <peer> --to <peer|-> "<text>" [--mentions a,b]
  eco peer history <room_id> [--limit N] [--after TS]        # 落库回放
  eco peer card <room_id>                                    # 房间卡片（含轮次/最后消息）
"""

import logging
import sys
from pathlib import Path

log = logging.getLogger("eco.peer")
logging.basicConfig(level=logging.INFO, format="%(message)s")
ROOT = Path(__file__).resolve().parent.parent.parent


def _bus() -> "PeerBus":  # noqa: F821  # 运行时 sys.path 注入后延迟导入，字符串注解不参与名称解析
    sys.path.insert(0, str(ROOT))
    from agent_core.eco_peer import PeerBus

    return PeerBus()


def build_parser(sub) -> None:
    p = sub.add_parser("peer", help="Agent 对等消息总线 / Bot 协作房间")
    subp = p.add_subparsers(dest="peer_action")

    p_register = subp.add_parser("register", help="注册/更新 peer")
    p_register.add_argument("peer_id")
    p_register.add_argument("--name", default=None)
    p_register.add_argument("--kind", default="agent", choices=["agent", "human"])
    p_register.add_argument("--transport", default=None)

    subp.add_parser("peers", help="列出已注册 peers")
    subp.add_parser("rooms", help="列出房间")

    p_create = subp.add_parser("create", help="创建房间")
    p_create.add_argument("name")
    p_create.add_argument("--member", action="append", default=[], dest="members")
    p_create.add_argument("--type", dest="room_type", default="group", choices=["group", "bot", "dm"])
    p_create.add_argument("--max-turns", type=int, default=None)
    p_create.add_argument("--owner", default=None)

    p_send = subp.add_parser("send", help="向房间发送消息（落库可回放）")
    p_send.add_argument("room_id")
    p_send.add_argument("text")
    p_send.add_argument("--from", dest="from_peer", required=True)
    p_send.add_argument("--to", dest="to_peer", default=None)
    p_send.add_argument("--kind", default=None, choices=[None, "group", "dm", "bot_reply"])
    p_send.add_argument("--mentions", default=None, help="逗号分隔 peer id")

    p_hist = subp.add_parser("history", help="回放房间消息")
    p_hist.add_argument("room_id")
    p_hist.add_argument("--limit", type=int, default=50)
    p_hist.add_argument("--after", default=None)

    p_card = subp.add_parser("card", help="房间卡片")
    p_card.add_argument("room_id")

    p_join = subp.add_parser("join", help="加入房间")
    p_join.add_argument("room_id")
    p_join.add_argument("peer_id")


def run(args) -> int:
    if not getattr(args, "peer_action", None):
        print("eco peer: need action (register/peers/rooms/create/send/history/card/join)")
        return 2
    bus = _bus()
    act = args.peer_action
    try:
        if act == "register":
            p = bus.register_peer(args.peer_id, name=args.name, kind=args.kind, transport=args.transport)
            print(f"peer {p['id']} registered  name={p['name']} kind={p['kind']}")
        elif act == "peers":
            for p in bus.list_peers():
                print(f"{p['id']:<16} {p['name']:<16} {p['kind']:<6} transport={p.get('transport') or '-'}")
        elif act == "rooms":
            for r in bus.list_rooms():
                print(
                    f"{r['id']}  {r['name']:<24} type={r['type']:<5} "
                    f"members={len(r['members'])} turns={r.get('max_turns') or '-'}"
                )
        elif act == "create":
            room = bus.create_room(
                args.name, members=args.members, room_type=args.room_type, max_turns=args.max_turns, owner=args.owner
            )
            print(f"room {room['id']} created  name={room['name']} type={room['type']} members={room['members']}")
        elif act == "send":
            mentions = None
            if getattr(args, "mentions", None):
                mentions = [m.strip() for m in args.mentions.split(",") if m.strip()]
            rec = bus.send(args.room_id, args.from_peer, args.text, to_peer=args.to_peer, kind=args.kind, mentions=mentions)
            limit = " [turn budget exceeded]" if rec["meta"].get("turn_exceeded") else ""
            print(f"{rec['msg_id']}  {rec['ts']}  {rec['from']} -> {rec['room_id']}{limit}")
        elif act == "history":
            msgs = bus.history(args.room_id, limit=args.limit, after_ts=args.after)
            if not msgs:
                print("(no messages)")
            for m in reversed(msgs):  # 时间正序展示
                line = f"[{m['ts']}] {m['from']}: {m['text']}"
                if m.get("mentions"):
                    line += f"  @{','.join(m['mentions'])}"
                if m["meta"].get("turn_exceeded"):
                    line += "  [turn budget exceeded]"
                print(line)
        elif act == "card":
            card = bus.room_card(args.room_id)
            print(
                f"room {card['id']}  {card['name']}  type={card['type']} "
                f"messages={card['message_count']} max_turns={card.get('max_turns') or '-'}"
            )
            print(f"members: {', '.join(card['members']) or '(none)'}")
            if card["last_message"]:
                lm = card["last_message"]
                print(f"last: [{lm['ts']}] {lm['from']}: {lm['text'][:80]}")
        elif act == "join":
            room = bus.join_room(args.room_id, args.peer_id)
            print(f"peer {args.peer_id} joined {room['id']} members={room['members']}")
    except KeyError as e:
        print(f"error: {e}")
        return 1
    return 0
