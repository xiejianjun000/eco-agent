#!/usr/bin/env python3
"""
eco/commands/cmd_monitor.py — 免 LLM 确定性巡检控制面（M4 P1-2 / Hermes monitor-mode 对标）
=============================================================================================
子命令：
  eco monitor run   [--script PATH] [--json]
                    一次巡检：确定性检查集 + 可选外部巡检脚本；输出检查表 + SIGNATURE。
  eco monitor watch [--interval SEC] [--ticks N] [--script PATH]
                    [--state FILE] [--alert-notepad]
                    循环巡检 + 基线签名比对：
                      no-change → 静默 tick（不唤醒 LLM）
                      change    → MONITOR CHANGE DETECTED（exit 2，供上层唤醒 LLM）
                    退出码：0 = 正常（健康 / 无变化 / 建立基线）；1 = 当前不健康；
                            2 = watch 检测到状态变更。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from agent_core.eco_monitor import (
    EcoMonitor,
)


def build_parser(sub) -> None:
    p = sub.add_parser("monitor", help="免 LLM 确定性巡检 (P1-2, monitor-mode 对标)")
    actions = p.add_subparsers(dest="action", required=True)

    a = actions.add_parser("run", help="一次巡检并输出签名")
    a.add_argument("--script", default=None, help="外部确定性巡检脚本（对标 monitor_script）")
    a.add_argument("--json", action="store_true")

    a = actions.add_parser("watch", help="循环巡检 + 基线签名变更检测")
    a.add_argument("--interval", type=float, default=60.0, help="巡检间隔秒")
    a.add_argument("--ticks", type=int, default=None, help="巡检轮数上限（默认无限）")
    a.add_argument("--script", default=None, help="外部确定性巡检脚本")
    a.add_argument("--state", default=None, help="基线状态文件（默认 ~/.eco/monitor_state.json）")
    a.add_argument("--alert-notepad", action="store_true", help="检测到变更时写入 notepad kind=alert")


def _render_table(report: dict, verbose: bool = False) -> None:
    print(f"eco monitor @ {report['ts']}  overall={'OK' if report['overall_ok'] else 'FAIL'}")
    for c in report["checks"]:
        mark = "OK " if c["ok"] else "FAIL"
        line = f"  [{mark}] {c['name']:<18} {c.get('detail', '')}"
        print(line[:200])


def run(args) -> int:
    mon = EcoMonitor(state_file=Path(args.state) if getattr(args, "state", None) else None)

    if args.action == "run":
        report = mon.run_once(script=args.script)
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            _render_table(report)
            print(f"SIGNATURE {report['signature']}")
        return 0 if report["overall_ok"] else 1

    if args.action == "watch":
        try:
            last = mon.watch(interval=args.interval, ticks=args.ticks, script=args.script, alert_notepad=args.alert_notepad)
        except KeyboardInterrupt:
            print("monitor watch interrupted")
            return 130
        status = last.get("status", "")
        if status == "change":
            return 2
        if not last.get("report", {}).get("overall_ok", True):
            return 1
        return 0

    print(f"unknown action {args.action}", file=sys.stderr)
    return 2
