"""
eco im - IM/网关接线（对标路线 M1 收尾：飞书/企微消息 → BotRoom 路由）

对标 Hermes：gateway 会话中 @Bot 路由、消息落 canonical Bot Chat、轮次预算抑制。

用法：
  eco im inject --channel feishu --chat oc_xxx --from ou_user1 --text "@bot-a 查空气质量"
                 [--chat-type group|p2p] [--title 群名] [--no-autojoin]
  eco im reply  --room r_xxx --from bot-a --text "回复内容" [--to peer]
  eco im map                                        # 列 IM 会话 → 房间映射

说明：本命令模拟 IM 平台事件注入（不持有真实飞书/企微凭据）；真实通道接入时，
把平台事件原样 POST 到 server 的 /api/v1/gateway/{channel} 即可复用同一路由。
"""

import json
import logging
import sys
from pathlib import Path

log = logging.getLogger("eco.im")
logging.basicConfig(level=logging.INFO, format="%(message)s")
ROOT = Path(__file__).resolve().parent.parent.parent


def _gw():
    sys.path.insert(0, str(ROOT))
    from agent_core.im_gateway import IMGateway

    return IMGateway()


def build_parser(sub) -> None:
    p = sub.add_parser("im", help="IM/网关接线（飞书/企微事件 → BotRoom 路由）")
    subp = p.add_subparsers(dest="im_action", required=True)

    p_inj = subp.add_parser("inject", help="模拟注入一条 IM 事件消息")
    p_inj.add_argument("--channel", default="feishu", choices=["feishu", "wecom", "http"])
    p_inj.add_argument("--chat", dest="chat_id", required=True, help="IM 会话 id（群/单聊）")
    p_inj.add_argument("--from", dest="sender", required=True, help="发送者 open_id/用户 id")
    p_inj.add_argument("--text", required=True)
    p_inj.add_argument("--chat-type", dest="chat_type", default="group", choices=["group", "p2p"])
    p_inj.add_argument("--title", default="")
    p_inj.add_argument("--no-autojoin", dest="autojoin", action="store_false", default=True)

    p_rep = subp.add_parser("reply", help="Bot 回复落库（kind=bot_reply，计入轮次预算）")
    p_rep.add_argument("--room", dest="room_id", required=True)
    p_rep.add_argument("--from", dest="from_peer", required=True)
    p_rep.add_argument("--text", required=True)
    p_rep.add_argument("--to", dest="to_peer", default=None)

    subp.add_parser("map", help="列出 IM 会话 → 房间映射")


def run(args) -> int:
    if not getattr(args, "im_action", None):
        print("eco im: need action (inject/reply/map)")
        return 2
    gw = _gw()
    act = args.im_action
    try:
        if act == "inject":
            if args.channel == "feishu":
                payload = {
                    "schema": "2.0",
                    "header": {"event_type": "im.message.receive_v1"},
                    "event": {
                        "message": {
                            "chat_id": args.chat_id,
                            "chat_type": args.chat_type,
                            "message_type": "text",
                            "content": json.dumps({"text": args.text}, ensure_ascii=False),
                        },
                        "sender": {"sender_id": {"open_id": args.sender}},
                    },
                }
                if args.title:
                    payload["event"]["message"]["chat"] = {
                        "chat_id": args.chat_id,
                        "chat_type": args.chat_type,
                        "name": args.title,
                    }
            elif args.channel == "wecom":
                payload = {
                    "ChatId": args.chat_id,
                    "FromUserName": args.sender,
                    "Content": args.text,
                    "msgtype": "text",
                    "chat_type": args.chat_type,
                }
                if args.title:
                    payload["ChatName"] = args.title
            else:  # http
                payload = {"room_key": args.chat_id, "from": args.sender, "text": args.text, "chat_type": args.chat_type}
                if args.title:
                    payload["title"] = args.title
            res = gw.deliver(args.channel, payload, autojoin=args.autojoin)
            if not res.get("ok"):
                print(f"error: {res.get('error')}")
                return 1
            print(
                f"delivered -> room {res['room_id']} ({res['room_name']}, "
                f"type={res['room_type']}, auto_created={res['auto_created']})"
            )
            print(f"  msg {res['message']['msg_id']}  mentions=@{','.join(res['mentions']) or '-'}")
            if res.get("unknown_mentions"):
                print(f"  unknown @: {', '.join(res['unknown_mentions'])}")
            if res["bot_replies"]:
                print("  bot_replies: " + ", ".join(r["to_peer"] for r in res["bot_replies"]))
            elif res["message"]["meta"].get("turn_exceeded"):
                print("  bot_replies: (轮次预算已超限，gateway 抑制 bot 回复)")
        elif act == "reply":
            rec = gw.reply(args.room_id, args.from_peer, args.text, to_peer=args.to_peer)
            limit = " [turn budget exceeded]" if rec["meta"].get("turn_exceeded") else ""
            print(f"{rec['msg_id']}  {rec['from']} -> {rec['room_id']}: {rec['text']}{limit}")
        elif act == "map":
            rows = gw.session_map()
            if not rows:
                print("(no IM session mapped yet)")
            for r in rows:
                print(f"{r['bus_key']:<40} -> {r['room_id']}  {r['room_name']} ({r['room_type']})")
        return 0
    except Exception as exc:
        print(f"error: {exc}")
        return 1
