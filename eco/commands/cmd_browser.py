#!/usr/bin/env python3
"""
eco/commands/cmd_browser.py — eco browser 子命令
=================================================
对标 Hermes 内置浏览器：eco browser open <url> / fetch <url> / shot <url> <png>
playwright 可用走真渲染，否则自动降级只读抓取（screenshot 明确不可用）。
"""

from __future__ import annotations

import argparse
import json


def build_parser(subp: argparse._SubParsersAction) -> None:
    p = subp.add_parser("browser", help="浏览器驱动（open/fetch/shot）")
    sub = p.add_subparsers(dest="browser_action", required=True)

    po = sub.add_parser("open", help="打开页面取 title+文本")
    po.add_argument("url")
    po.add_argument("--wait-ms", type=int, default=800)
    po.add_argument("--json", action="store_true")

    pf = sub.add_parser("fetch", help="只读抓取正文文本")
    pf.add_argument("url")
    pf.add_argument("--json", action="store_true")

    ps = sub.add_parser("shot", help="截图保存 PNG（需 playwright）")
    ps.add_argument("url")
    ps.add_argument("out_path")


def run(args: argparse.Namespace) -> int:
    from agent_core.browser_tool import get_browser

    b = get_browser()
    act = args.browser_action
    if act == "open":
        r = b.open(args.url, wait_ms=getattr(args, "wait_ms", 800))
    elif act == "fetch":
        r = b.fetch_text(args.url)
    elif act == "shot":
        r = b.screenshot(args.url, args.out_path)
    else:
        print(f"未知 browser 动作: {act}")
        return 1

    if getattr(args, "json", False) or act == "shot":
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0 if r.get("ok") else 1

    if not r.get("ok"):
        print(f"[X] driver={r.get('driver')} error={r.get('error')}")
        return 1
    print(f"[OK] driver={r.get('driver')} title={r.get('title', '')!r}")
    if r.get("url"):
        print(f"     url={r['url']}")
    if r.get("text"):
        print("----- text -----")
        print(r["text"])
    if r.get("path"):
        print(f"     saved={r['path']} ({r.get('bytes', 0)}B)")
    return 0
