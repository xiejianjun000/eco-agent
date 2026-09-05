"""
eco task - L2 任务调度层控制面（P0-2）

对标 Hermes Live Steering：
  eco task list                      # 查看运行中/最近 mission
  eco task run "<goal>"              # 前台执行 mission（可被另一终端 stop/steer）
  eco task stop <id> [--keep-partial]  # 停止；默认保留已完成部分结果
  eco task steer <id> "<instruction>" # 向运行中 mission 下发纠偏指令
  eco task show <id>                 # 查看 mission 子任务明细
"""

import logging
import sys
from pathlib import Path

log = logging.getLogger("eco.task")
logging.basicConfig(level=logging.INFO, format="%(message)s")
ROOT = Path(__file__).resolve().parent.parent.parent


def _control() -> "TaskControl":  # noqa: F821  # 运行时 sys.path 注入后延迟导入，字符串注解不参与名称解析
    sys.path.insert(0, str(ROOT))
    from agent_core.task_control import TaskControl

    return TaskControl()


def _fmt_status(st: str) -> str:
    marks = {"pending": "·", "running": "▶", "completed": "✓", "failed": "✗", "skipped": "⊘", "blocked": "▣"}
    return f"{marks.get(st, '?')} {st:<9}"


def _print_mission(m: dict, verbose: bool = False) -> None:
    print(f"\nmission {m.get('id')}  [{m.get('status')}]  pid={m.get('pid')}")
    print(f"  goal    : {m.get('goal', '')[:100]}")
    print(f"  created : {m.get('created_at')}  updated: {m.get('updated_at')}")
    if m.get("note"):
        print(f"  note    : {m['note']}")
    if verbose:
        for t in m.get("tasks", []):
            v = f"  verdict: {t.get('verdict', '')[:100]}" if t.get("verdict") else ""
            print(f"    {_fmt_status(t.get('status', ''))} {t.get('id', '')}  {t.get('description', '')[:80]}{v}")


def run(args):
    action = args.action
    ctl = _control()

    if action == "list":
        missions = ctl.list_missions(limit=args.limit)
        if not missions:
            print("暂无任务记录（运行 eco task run 产生）")
            return 0
        for m in missions:
            _print_mission(m)
        return 0

    if action == "show":
        m = ctl.get(args.mission_id)
        if not m:
            print(f"未找到 mission: {args.mission_id}")
            return 1
        _print_mission(m, verbose=True)
        return 0

    if action == "stop":
        if not args.mission_id:
            print("请指定 mission id: eco task stop <id> [--keep-partial]")
            return 1
        r = ctl.stop(args.mission_id, keep_partial=args.keep_partial)
        if not r.get("found"):
            print(f"未找到 mission: {args.mission_id}")
            return 1
        mode = "保留已完成部分结果" if args.keep_partial else "全部丢弃"
        print(f"[task] 已向 {args.mission_id} 下发停止信号（{mode}），下一波前生效")
        return 0

    if action == "steer":
        if not args.mission_id or not args.instruction:
            print('请指定 mission id 与纠偏指令: eco task steer <id> "<instruction>"')
            return 1
        r = ctl.steer(args.mission_id, args.instruction)
        if not r.get("found"):
            print(f"未找到 mission: {args.mission_id}")
            return 1
        print(f"[task] 已向 {args.mission_id} 下发纠偏指令，下一波任务将携带该上下文")
        return 0

    if action == "run":
        goal = args.goal
        if not goal:
            print('请指定目标: eco task run "<goal>"')
            return 1
        sys.path.insert(0, str(ROOT))
        try:
            from agent_core.commander_v2 import CommanderV2
        except Exception as e:
            log.error(f"无法加载 CommanderV2: {e}")
            return 1
        mid = ctl.begin(goal)
        print(f"[task] mission {mid} 开始: {goal[:80]}")
        print("[task] 控制方式（另一终端）:")
        print(f"       eco task stop {mid} --keep-partial")
        print(f'       eco task steer {mid} "改为优先离线评估"')
        try:
            commander = CommanderV2(
                max_steer_rounds=getattr(args, "max_rounds", 3), schema_validate=not getattr(args, "no_schema", False)
            )
            summary = commander.execute(goal, control=ctl)
            if summary:
                print("\n[task] mission 摘要:")
                print(f"  status     : {summary.get('status')}")
                print(f"  completed  : {summary.get('completed', 0)}  failed: {summary.get('failed', 0)}")
                print(f"  skipped    : {summary.get('skipped', 0)}  elapsed_ms: {summary.get('total_time_ms')}")
                if summary.get("schema_validate"):
                    print(f"  schema     : 校验开启  rejected={summary.get('schema_rejected', 0)}")
                    print(f"  steer      : {summary.get('steer_rounds_total', 0)}/{summary.get('steer_budget', 3)} 轮")
                ledger = summary.get("cost_ledger") or {}
                if ledger.get("delegations"):
                    print(
                        f"  cost       : delegations={ledger['delegations']} "
                        f"tokens={ledger.get('total_tokens', 0)} "
                        f"cost=${ledger.get('total_cost_usd', 0)}"
                    )
            ctl.finish(mid, status="finished")
            print(f"[task] mission {mid} 完成，详情: eco task show {mid}")
        except KeyboardInterrupt:
            ctl.finish(mid, status="interrupted", note="KeyboardInterrupt")
            print(f"\n[task] mission {mid} 被中断，已完成子任务保留: eco task show {mid}")
            return 130
        return 0

    log.error(f"未知动作: {action}")
    return 1


def build_parser(sub) -> None:
    p = sub.add_parser("task", help="L2 任务调度控制面：list/run/stop --keep-partial/steer/show")
    subp = p.add_subparsers(dest="action", required=True)

    pl = subp.add_parser("list", help="列出运行中/最近 mission")
    pl.add_argument("--limit", type=int, default=20)

    pr = subp.add_parser("run", help="前台执行 L2 mission（支持另一终端控制）")
    pr.add_argument("goal", nargs="?", default=None, help="任务目标 goal")
    pr.add_argument("--max-rounds", type=int, default=3, metavar="N", help="Steering 深化：operator steer 迭代预算（默认 3）")
    pr.add_argument("--no-schema", action="store_true", help="Steering 深化：关闭子任务 JSON Schema I/O 校验")

    ps = subp.add_parser("stop", help="停止 mission（默认 --keep-partial 保留部分结果）")
    ps.add_argument("mission_id", nargs="?", default=None)
    ps.add_argument("--keep-partial", action="store_true", default=True, help="保留已完成子任务的部分产出（默认开启）")
    ps.add_argument("--discard", dest="keep_partial", action="store_false", help="不保留部分产出（等价全量丢弃）")

    pe = subp.add_parser("steer", help="向运行中 mission 下发纠偏指令")
    pe.add_argument("mission_id", nargs="?", default=None)
    pe.add_argument("instruction", nargs="?", default=None)

    psh = subp.add_parser("show", help="查看 mission 子任务明细")
    psh.add_argument("mission_id", nargs="?", default=None)
