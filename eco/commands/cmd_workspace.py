#!/usr/bin/env python3
"""eco workspace - 项目工作区管理（Phase B1）"""

import json


def run(args):
    from agent_core.workspace import get_workspace_manager

    mgr = get_workspace_manager()

    if args.action == "create":
        if not args.name:
            print("用法: eco workspace create <名称>")
            return 1
        try:
            ws = mgr.create(args.name)
        except FileExistsError as e:
            print(f"[workspace] {e}")
            return 1
        mgr.open(ws.meta["slug"])
        print(f"[workspace] 已创建并打开: {args.name}  ({ws.path})")
        return 0

    if args.action == "list":
        items = mgr.list()
        if not items:
            print("[workspace] 暂无工作区")
            return 0
        cur = mgr.current_name()
        for m in items:
            mark = "*" if m.get("slug") == cur else " "
            print(
                f"{mark} {m.get('name')}  slug={m.get('slug')}  事件数={m.get('n_events', 0)}"
                f"  最近活跃={m.get('updated_at', '')}"
            )
        return 0

    if args.action == "open":
        if not args.name:
            print("用法: eco workspace open <名称或slug>")
            return 1
        ws = mgr.open(args.name)
        if not ws:
            print(f"[workspace] 未找到: {args.name}")
            return 1
        print(f"[workspace] 已打开: {ws.meta.get('name')}  ({ws.path})")
        return 0

    if args.action == "close":
        cur = mgr.close()
        if cur:
            print(f"[workspace] 已关闭: {cur}")
        else:
            print("[workspace] 当前无打开的工作区")
        return 0

    if args.action == "show":
        ws = mgr.get(args.name) if args.name else mgr.current()
        if not ws:
            print("[workspace] 未指定或未找到工作区")
            return 1
        m = ws.meta
        print(f"名称: {m.get('name')}  slug: {m.get('slug')}")
        print(f"创建: {m.get('created_at')}  最近活跃: {m.get('updated_at')}")
        print(f"目录: {ws.path}")
        print("--- 摘要 ---")
        print(ws.summary())
        return 0

    if args.action == "freeze":
        ws = mgr.get(args.name) if args.name else mgr.current()
        if not ws:
            print("[workspace] 未指定或未找到工作区")
            return 1
        r = mgr.freeze_to_memory_tree(ws)
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0 if r.get("ok") else 1

    print(f"未知 action: {args.action}")
    return 1
