#!/usr/bin/env python3
"""
eco/commands/cmd_state.py — 状态可移植控制面（M4 P1-1 / hermes_state 对标）
========================================================================
子命令：
  eco state list                枚举状态源 holder + 健康探测（registry/holders）
  eco state inspect KEY         单源状态摘要
  eco state search QUERY       统一检索 memory-tree / memory jsonl / 文本源
  eco state export [--scope] [--out FILE] [--include-absent]   导出 bundle
  eco state validate FILE       bundle schema + 哈希/编码深校验
  eco state import FILE [--dry-run] [--force] [--scope]        还原 bundle
                                （--eco-root/--home-root 可重定向目标实例）
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from agent_core import eco_state as st
from agent_core.eco_state import (
    ECO_STATE_SCHEMA_VERSION,
    EcoStatePortability,
    EcoStateRegistry,
    EcoStateSearch,
)


def build_parser(sub) -> None:
    p = sub.add_parser("state", help="状态可移植控制面 (P1-1)")
    actions = p.add_subparsers(dest="action", required=True)

    a = actions.add_parser("list", help="枚举状态源 holder + 健康")
    a.add_argument("--json", action="store_true")

    a = actions.add_parser("inspect", help="单源状态摘要")
    a.add_argument("key")
    a.add_argument("--json", action="store_true")

    a = actions.add_parser("search", help="统一状态检索")
    a.add_argument("query")
    a.add_argument("--k", type=int, default=5)
    a.add_argument("--holder", action="append", default=None, help="限定状态源（可多次），默认全部")

    a = actions.add_parser("export", help="导出版本化可移植 bundle")
    a.add_argument("--scope", choices=["core", "home", "all"], default="all")
    a.add_argument("--out", default=None, metavar="FILE")
    a.add_argument("--include-absent", action="store_true", help="不存在的 holder 也写入 entry(present=false)")

    a = actions.add_parser("validate", help="校验 bundle")
    a.add_argument("file")

    a = actions.add_parser("import", help="还原 bundle（默认 dry-run 预览）")
    a.add_argument("file")
    a.add_argument("--scope", choices=["core", "home", "all"], default="all")
    a.add_argument("--dry-run", action="store_true", help="只打印还原计划不写盘（默认开启，见 --commit）")
    a.add_argument("--commit", action="store_true", help="实际写盘还原")
    a.add_argument("--force", action="store_true", help="允许覆盖已存在的目标文件")
    a.add_argument("--eco-root", default=None, help="目标实例 eco 根")
    a.add_argument("--home-root", default=None, help="目标实例 home 根")


def _cmd_list(args) -> int:
    reg = EcoStateRegistry()
    probes = reg.list()
    summary = reg.summary()
    if args.json:
        print(json.dumps({"summary": summary, "holders": probes}, ensure_ascii=False, indent=2))
        return 0
    print(
        f"eco state schema v{ECO_STATE_SCHEMA_VERSION} — "
        f"holders {summary['holders_total']} total, "
        f"{summary['holders_present']} present, "
        f"{summary['holders_healthy']} healthy, "
        f"{summary['record_count_total']} records"
    )
    header = f"{'KEY':<16}{'SCOPE':<6}{'KIND':<7}{'HEALTH':<9}{'REC':>6}  PATH"
    print(header)
    print("-" * len(header))
    for probe in probes:
        health = "ok" if probe["healthy"] else ("-" if not probe["present"] else "BAD")
        print(
            f"{probe['key']:<16}{probe['scope']:<6}{probe['kind']:<7}"
            f"{health:<9}{probe['record_count']:>6}  "
            f"{probe['relpath']}{'  [' + str(probe['error']) + ']' if probe['error'] else ''}"
        )
    return 0


def _cmd_inspect(args) -> int:
    reg = EcoStateRegistry()
    if args.key not in reg.holders:
        print(f"未知 holder: {args.key}（可用: {', '.join(sorted(reg.holders))}）", file=sys.stderr)
        return 2
    probe = reg.probe(args.key)
    if args.json:
        print(json.dumps(probe, ensure_ascii=False, indent=2))
        return 0
    print(json.dumps(probe, ensure_ascii=False, indent=2))
    return 0


def _cmd_search(args) -> int:
    search = EcoStateSearch()
    out = search.search(args.query, k=args.k, holders=args.holder)
    if not out:
        print(f"无命中（query={args.query!r}）")
        return 0
    for key, hits in out.items():
        print(f"\n[{key}] {len(hits)} hits")
        for i, h in enumerate(hits, 1):
            meta = {kk: vv for kk, vv in h.items() if kk != "snippet"}
            print(f"  {i}. {json.dumps(meta, ensure_ascii=False)}")
            print(f"     {h['snippet']}")
    return 0


def _cmd_export(args) -> int:
    p = EcoStatePortability()
    bundle = p.export_bundle(scope=args.scope, include_absent=args.include_absent)
    out_path = Path(args.out) if args.out else None
    if out_path is None:
        out_dir = st.PROJECT_ROOT / "output"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / ("eco-state-export-" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".json")
    p.write_bundle(bundle, out_path)
    ok, errs = p.validate_bundle(bundle)
    print(f"exported {len(bundle['entries'])} entries, schema v{bundle['schema_version']} → {out_path}")
    print(f"bundle validate: {'OK' if ok else 'FAILED'}")
    for err in errs[:10]:
        print("  -", err)
    return 0 if ok else 1


def _cmd_validate(args) -> int:
    p = EcoStatePortability()
    try:
        bundle = p.load_bundle_file(Path(args.file))
    except Exception as exc:  # noqa: BLE001
        print(f"校验失败: {exc}", file=sys.stderr)
        return 1
    print(
        f"bundle OK: {bundle['source']} @ {bundle['exported_at']} eco={bundle['eco_version']} entries={len(bundle['entries'])}"
    )
    return 0


def _cmd_import(args) -> int:
    p = EcoStatePortability()
    try:
        bundle = p.load_bundle_file(Path(args.file))
    except Exception as exc:  # noqa: BLE001
        print(f"bundle 加载失败: {exc}", file=sys.stderr)
        return 1
    dry_run = not args.commit
    plan = p.plan_import(bundle, target_eco_root=args.eco_root, target_home_root=args.home_root, scope=args.scope)
    creates = [i for i in plan if i["action"] == "create"]
    overwrites = [i for i in plan if i["action"] == "overwrite"]
    print(
        f"还原计划: {len(plan)} 文件 ({len(creates)} create / {len(overwrites)} overwrite)" + (" [dry-run]" if dry_run else "")
    )
    for item in plan[:60]:
        flag = "C" if item["action"] == "create" else "O"
        print(f"  [{flag}] {item['scope']}:{item['key']}/{item['file']} → {item['dst']}")
    if len(plan) > 60:
        print(f"  ... 其余 {len(plan) - 60} 个文件省略")
    if dry_run:
        if not args.force and overwrites:
            print("\n提示: 存在将覆盖的文件；--commit 实际写盘，--force 允许覆盖。")
        print("（dry-run 模式，未写盘；加 --commit 实际还原）")
        return 0
    if overwrites and not args.force:
        print(f"中止: {len(overwrites)} 个目标已存在，需 --force 才允许覆盖。", file=sys.stderr)
        return 1
    stats = p.import_bundle(
        bundle,
        target_eco_root=args.eco_root,
        target_home_root=args.home_root,
        scope=args.scope,
        dry_run=False,
        force=args.force,
    )
    print(f"还原完成: created={stats['created']} overwritten={stats['overwritten']} skipped={stats['skipped_existing']}")
    return 0


def run(args) -> int:
    handlers = {
        "list": _cmd_list,
        "inspect": _cmd_inspect,
        "search": _cmd_search,
        "export": _cmd_export,
        "validate": _cmd_validate,
        "import": _cmd_import,
    }
    fn = handlers.get(args.action)
    if fn is None:
        print(f"未知 state 子命令: {args.action}", file=sys.stderr)
        return 2
    return fn(args)
