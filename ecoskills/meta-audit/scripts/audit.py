#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ecoskills/meta-audit/scripts/audit.py — 技能自审（self-audit 元技能）
===================================================================
对 ecoskills/<name>/SKILL.md 做 10 项质量审计，输出评分卡。
评分 <70 判定不合格（CI 硬门禁候选）。对标 Greater-China-Legal self-audit。

用法:
  python3 ecoskills/meta-audit/scripts/audit.py <技能名> [--json]
  python3 ecoskills/meta-audit/scripts/audit.py --all [--json] [--min 70]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent
SKILLS_DIR = ROOT / "ecoskills"

CHECK_LABELS = [
    "frontmatter-name", "description 完整", "触发词", "风险标注",
    "工作流", "决策表/清单", "输出格式", "引用纪律", "引用路径真实", "篇幅合理",
]


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
    if not m:
        return {}, text
    meta: dict = {}
    for line in m.group(1).splitlines():
        line = line.strip()
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    return meta, m.group(2)


def audit_skill(name: str) -> dict:
    skill_dir = SKILLS_DIR / name
    md = skill_dir / "SKILL.md"
    if not md.exists():
        return {"skill": name, "exists": False, "score": 0,
                "checks": [{"item": "存在", "ok": False, "note": "SKILL.md 不存在"}]}
    text = md.read_text(encoding="utf-8")
    meta, body = _parse_frontmatter(text)

    checks = []
    def add(item: str, ok: bool, note: str = "") -> None:
        checks.append({"item": item, "ok": ok, "note": note})

    desc = meta.get("description", "")
    add("frontmatter-name", bool(meta.get("name")), meta.get("name", "缺失"))
    add("description 完整", len(desc) >= 20, f"{len(desc)} 字")
    has_trigger = ("触发词" in desc) or bool(meta.get("trigger_phrases"))
    add("触发词", has_trigger, "description 含触发词" if "触发词" in desc else "无")
    risk = meta.get("risk_level", "")
    has_forbidden = any(k in body for k in ("禁用领域", "严格限制", "⚠️"))
    add("风险标注", bool(risk) and (risk != "high" or has_forbidden),
        f"risk_level={risk or '缺失'}" + ("，含禁用领域" if has_forbidden else "，无禁用领域"))
    add("工作流", bool(re.search(r"Step\s*\d", body)) or "工作流程" in body)
    add("决策表/清单", bool(re.search(r"^\|.+\|$", body, re.M)))
    add("输出格式", "输出格式" in body or "```" in body)
    add("引用纪律", any(k in body for k in ("statute_lookup", "待确认", "核实原文", "来源")))
    # 引用路径真实性：正文中出现的 references/xxx 或 scripts/xxx 必须在磁盘存在
    refs = set(re.findall(r"(?:references|scripts)/[\w./-]+", body))
    missing_refs = [r for r in refs if not (skill_dir / r).exists()]
    add("引用路径真实", not missing_refs,
        "缺失: " + ", ".join(missing_refs) if missing_refs else "全部存在")
    # 篇幅上限 2026-08 由 8000 上调至 12000：gongwen-draft 正文 8623 字、含 16 份
    # references 与 15 个 scripts 的完整工作流，8000 上限过紧导致误伤合法长技能。
    add("篇幅合理", 300 <= len(body) <= 12000, f"正文 {len(body)} 字")

    score = sum(10 for c in checks if c["ok"])
    return {"skill": name, "exists": True, "score": score,
            "max": len(checks) * 10, "checks": checks,
            "pass": score >= 70}


def main() -> None:
    ap = argparse.ArgumentParser(description="eco-agent 技能自审")
    ap.add_argument("target", nargs="?", help="技能名；--all 则全库")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--min", type=int, default=70)
    args = ap.parse_args()

    if args.all:
        names = sorted(d.name for d in SKILLS_DIR.iterdir()
                       if d.is_dir() and (d / "SKILL.md").exists())
        results = [audit_skill(n) for n in names]
    else:
        if not args.target:
            print("用法: audit.py <技能名> | audit.py --all")
            sys.exit(2)
        results = [audit_skill(args.target)]

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=1))
    else:
        for r in results:
            if not r.get("exists"):
                print(f"❌ {r['skill']}: SKILL.md 不存在")
                continue
            mark = "✅" if r["pass"] else "❌"
            print(f"{mark} {r['skill']}: {r['score']}/{r['max']} 分")
            for c in r["checks"]:
                if not c["ok"]:
                    print(f"   ✗ {c['item']} — {c['note']}")
        print(f"\n合计: {sum(1 for r in results if r.get('pass'))}/{len(results)} 通过"
              f"（门槛 {args.min} 分）")
    sys.exit(0 if all(r.get("pass") for r in results) else 1)


if __name__ == "__main__":
    main()
