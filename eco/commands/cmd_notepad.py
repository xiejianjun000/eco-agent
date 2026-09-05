#!/usr/bin/env python3
"""
eco/commands/cmd_notepad.py — 结构化便签控制面（M4 P1-2 / Hermes cron notepad 对标）
=====================================================================================
子命令：
  eco notepad add TITLE [--content C] [--tags a,b] [--kind note|scratch|alert] [--ref ID]
  eco notepad list  [--tag T] [--limit N] [--archived] [--json]
  eco notepad get   ID [--json]
  eco notepad search QUERY [--tag T] [--archived] [--json]
  eco notepad archive ID
  eco notepad stats [--json]
"""

from __future__ import annotations

import json
import sys

from agent_core.eco_notepad import VALID_KINDS, NotepadStore


def build_parser(sub) -> None:
    p = sub.add_parser("notepad", help="结构化便签簿 (P1-2, Hermes notepad 对标)")
    actions = p.add_subparsers(dest="action", required=True)

    a = actions.add_parser("add", help="新增一条结构化便签")
    a.add_argument("title")
    a.add_argument("--content", default="")
    a.add_argument("--tags", default=None, help="逗号分隔标签")
    a.add_argument("--kind", choices=list(VALID_KINDS), default="note")
    a.add_argument("--ref", default=None, help="关联对象 id（task/peer/scheduled_job）")

    a = actions.add_parser("list", help="枚举便签")
    a.add_argument("--tag", default=None)
    a.add_argument("--limit", type=int, default=None)
    a.add_argument("--archived", action="store_true")
    a.add_argument("--json", action="store_true")

    a = actions.add_parser("get", help="查看单条便签")
    a.add_argument("note_id")
    a.add_argument("--json", action="store_true")

    a = actions.add_parser("search", help="全文检索便签")
    a.add_argument("query")
    a.add_argument("--tag", default=None)
    a.add_argument("--archived", action="store_true")
    a.add_argument("--json", action="store_true")

    a = actions.add_parser("archive", help="归档便签（只标记不删除）")
    a.add_argument("note_id")

    a = actions.add_parser("stats", help="便签簿统计")
    a.add_argument("--json", action="store_true")


def _print_note(n: dict, verbose: bool = True) -> None:
    print(f"[{n['id']}] ({n['kind']}{' archived' if n.get('archived') else ''}) {n['title']}  @{n['created_at']}")
    if n.get("tags"):
        print(f"    tags: {','.join(n['tags'])}")
    if n.get("ref"):
        print(f"    ref : {n['ref']}")
    if verbose and n.get("content"):
        for line in n["content"].splitlines():
            print(f"    | {line}")


def run(args) -> int:
    store = NotepadStore()
    if args.action == "add":
        tags = [t.strip() for t in (args.tags or "").split(",") if t.strip()]
        note = store.add(args.title, content=args.content, tags=tags, kind=args.kind, ref=args.ref)
        print(f"added {note['id']} → {store.path}")
        return 0

    if args.action == "list":
        notes = store.list(tag=args.tag, include_archived=args.archived, limit=args.limit)
        if args.json:
            print(json.dumps(notes, ensure_ascii=False, indent=2))
            return 0
        print(f"notepad {store.path} — {len(notes)} notes")
        for n in notes:
            _print_note(n, verbose=False)
        return 0

    if args.action == "get":
        n = store.get(args.note_id)
        if n is None:
            print(f"note {args.note_id} 不存在", file=sys.stderr)
            return 1
        if args.json:
            print(json.dumps(n, ensure_ascii=False, indent=2))
            return 0
        _print_note(n, verbose=True)
        return 0

    if args.action == "search":
        hits = store.search(args.query, tag=args.tag, include_archived=args.archived)
        if args.json:
            print(json.dumps(hits, ensure_ascii=False, indent=2))
            return 0
        print(f"搜索 {args.query!r} — {len(hits)} hits")
        for n in hits:
            _print_note(n, verbose=False)
        return 0

    if args.action == "archive":
        if store.archive(args.note_id):
            print(f"archived {args.note_id}")
            return 0
        print(f"note {args.note_id} 不存在或已归档", file=sys.stderr)
        return 1

    if args.action == "stats":
        s = store.stats()
        if args.json:
            print(json.dumps(s, ensure_ascii=False, indent=2))
            return 0
        print(f"file    : {s['file']}")
        print(f"exists  : {s['exists']}")
        print(f"size    : {s['size_bytes']} B")
        print(f"total   : {s['total']} (archived {s['archived']})")
        print(f"by_kind : {json.dumps(s['by_kind'], ensure_ascii=False)}")
        return 0

    print(f"unknown action {args.action}", file=sys.stderr)
    return 2
