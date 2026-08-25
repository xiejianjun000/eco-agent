#!/usr/bin/env python3
"""
_scripts/verify_ops.py — 7×24 运维体检（路径③验证脚本）

日常跑一遍（cron 或心跳触发），检查 Eco Agent 的持续进化与记忆健康：
  1. 会话日志完整性（SessionEventLog.verify，全会话链校验）
  2. 进化报告存在性与篇幅（≥500 字，验收 I-01）
  3. 记忆树漂移（节点数/热节点/评分分布）
  4. 记忆矛盾状态（open/resolved，验收 A-04）
  5. 技能库变化（数量/A-B 快照）

用法:
  python _scripts/verify_ops.py             # 输出体检报告
  python _scripts/verify_ops.py --json      # JSON 输出（供 cron 采集）
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

REPORT_FILE = ROOT / "evolution_report.md"


def check_session_logs() -> dict:
    from agent_core.session_log import list_sessions

    sessions = list_sessions()
    ok = all(s["ok"] for s in sessions)
    return {
        "sessions": len(sessions),
        "events_total": sum(s["events"] for s in sessions),
        "all_verified": ok,
        "truncated_total": sum(s["truncated"] for s in sessions),
    }


def check_evolution_report() -> dict:
    # 口径统一：优先查版本化报告 evolution_report_v{N}.md（meta_evolution 实际产出），
    # 回退未版本化的 evolution_report.md（历史口径）。
    versioned = sorted(ROOT.glob("evolution_report_v*.md"), key=lambda p: p.name)
    target = versioned[-1] if versioned else None
    if target is None and REPORT_FILE.is_file():
        target = REPORT_FILE
    if target is None:
        return {"exists": False, "chars": 0, "pass": False, "note": "evolution_report 不存在（未触发过进化）"}
    text = target.read_text(encoding="utf-8", errors="replace")
    return {"exists": True, "chars": len(text), "pass": len(text) >= 500,
            "note": ("I-01 口径: 每次进化 ≥500 字" if len(text) >= 500 else "篇幅不足 500 字"),
            "report_file": str(target)}


def check_memory_tree() -> dict:
    try:
        from _scripts.memory_tree import MemoryTree

        tree = MemoryTree()
        stats = tree.get_stats()
        hot = tree.get_hot_nodes(limit=10)
        return {
            "total_nodes": stats["total_nodes"],
            "total_edges": stats["total_edges"],
            "hot_top": [{"title": n.get("title", n["id"])[:40], "score": n.get("score", 0)} for n in hot],
        }
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


def check_conflicts() -> dict:
    try:
        from agent_core.memory_curation import get_memory_curator

        return get_memory_curator().stats()
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


def check_trace_audit() -> dict:
    """执行轨迹审计链（govmcp SM3）完整性——等保三级台账项。"""
    try:
        from agent_core.trace_audit import get_trace_audit

        audit = get_trace_audit()
        return audit.stats()
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


def check_skills() -> dict:
    try:
        from agent_core.skill_system import SkillRegistry

        reg = SkillRegistry()
        return {"skill_count": len(reg.list_by_category("")), "stats": reg.get_stats()}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


def run_checks() -> dict:
    return {
        "checked_at": datetime.now().isoformat(),
        "session_logs": check_session_logs(),
        "trace_audit": check_trace_audit(),
        "evolution_report": check_evolution_report(),
        "memory_tree": check_memory_tree(),
        "memory_conflicts": check_conflicts(),
        "skills": check_skills(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Eco Agent 7×24 运维体检")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    report = run_checks()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    print("═" * 60)
    print("ECO AGENT 7×24 运维体检")
    print(f"  时间: {report['checked_at']}")
    sl = report["session_logs"]
    print(f"\n[会话日志] {sl['sessions']} 个会话 / {sl['events_total']} 事件 / "
          f"校验{'通过' if sl['all_verified'] else '异常'} / 截断 {sl['truncated_total']}")
    ta = report["trace_audit"]
    if "error" in ta:
        print(f"[轨迹审计] 异常: {ta['error']}")
    else:
        print(f"[轨迹审计] {ta['entries']} 条 / SM3 链{'✅ 完整' if ta['ok'] else '❌ 断裂'} / "
              f"尾哈希 {ta.get('last_hash', '')}")
    er = report["evolution_report"]
    print(f"[进化报告] {'存在' if er['exists'] else '缺失'} / {er['chars']} 字 / "
          f"{'✅ 达标' if er['pass'] else '⚠️ ' + er['note']}")
    mt = report["memory_tree"]
    if "error" in mt:
        print(f"[记忆树] 异常: {mt['error']}")
    else:
        hot_label = ", ".join(f"{h['title']}({h['score']})" for h in mt["hot_top"][:3])
        print(f"[记忆树] {mt['total_nodes']} 节点 / {mt['total_edges']} 边 / 热榜: {hot_label}")
    mc = report["memory_conflicts"]
    if "error" in mc:
        print(f"[记忆矛盾] 异常: {mc['error']}")
    else:
        print(f"[记忆矛盾] 开放 {mc['open_conflicts']} / 已消解 {mc['resolved_conflicts']} / "
              f"审计 {mc['audit_entries']} 条")
    sk = report["skills"]
    if "error" in sk:
        print(f"[技能库] 异常: {sk['error']}")
    else:
        print(f"[技能库] {sk['skill_count']} 个技能")
    print("═" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
