#!/usr/bin/env python3
"""
ecoskills/meta-interview/scripts/interview.py — 访谈式技能冷启动
================================================================
把老师傅的隐性执法经验显性化为 SKILL.md 骨架（cold-start-interview 元技能）。

用法:
  python3 interview.py <技能名> --print                    # 打印 8 问（访谈用）
  python3 interview.py <技能名> --answers answers.json      # 批量模式：从 JSON 生成骨架
  python3 interview.py <技能名>                             # 交互式逐问（真实终端）

answers.json 格式: {"q1": "...", "q2": "...", ... "q8": "..."}（可为空串跳过）
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent
SKILLS_DIR = ROOT / "ecoskills"

QUESTIONS = [
    ("q1", "这个技能叫什么？一句话说明它解决什么执法场景？"),
    ("q2", "触发场景是什么（用户会怎么问）？触发词有哪些（逗号分隔）？"),
    ("q3", "老手做这件事的标准流程分几步？每步的关键动作？"),
    ("q4", "有没有必须查的时限/数值/表格（如 5 日内听证申请、超标倍数阶次）？"),
    ("q5", "最容易出错/最容易被忽视的坑有哪些（3 条以上）？"),
    ("q6", "有没有绝对不能做的红线（禁用领域）？"),
    ("q7", "产出的标准格式是什么（文书结构/意见格式）？"),
    ("q8", "有没有现成的参考文件（模板/基准文件/历史案例路径）？"),
]


def _build_skill(name: str, answers: dict) -> str:
    desc_part = answers.get("q2", "").strip()
    trig = ""
    if "，" in desc_part or "、" in desc_part:
        parts = [p.strip() for p in re.split(r"[，、]", desc_part) if p.strip()]
        trig = "。触发词：" + "、".join(parts[:6])
    lines = [
        "---",
        f"name: {name}",
        f"description: {answers.get('q1', '').strip()}（{desc_part[:120]}）{trig}",
        "risk_level: high",
        "version: 1.0.0",
        "---",
        "",
        f"# /{name} — {answers.get('q1', '').strip()[:40]}",
        "",
        "## 核心原则",
        "",
        "> （待军哥补一句原则性表述）",
        "",
        "## 工作流程",
        "",
        "```",
        (answers.get("q3", "").strip() or "Step 1: （待补）"),
        "```",
        "",
        "## 决策表 / 关键数值",
        "",
        answers.get("q4", "").strip() or "（待补：时限/数值表）",
        "",
        "## 常见坑（来自老师傅访谈）",
        "",
        answers.get("q5", "").strip() or "（待补）",
        "",
        "## 禁用领域",
        "",
        "```",
        answers.get("q6", "").strip() or "⚠️ （待补：红线条目）",
        "```",
        "",
        "## 输出格式",
        "",
        "```",
        answers.get("q7", "").strip() or "【输出结构】（待补）",
        "```",
        "",
        "## 参考文件",
        "",
        answers.get("q8", "").strip() or "（无）",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="访谈式技能冷启动")
    ap.add_argument("name", help="新技能名（目录名，如 scene-xxx）")
    ap.add_argument("--print", dest="print_questions", action="store_true", help="仅打印 8 问")
    ap.add_argument("--answers", help="answers.json 路径（批量模式）")
    args = ap.parse_args()

    if args.print_questions:
        for key, q in QUESTIONS:
            print(f"{key}: {q}")
        return

    answers: dict = {}
    if args.answers:
        answers = json.loads(Path(args.answers).read_text(encoding="utf-8"))
    else:
        print("逐问回答（回车跳过）。Ctrl+C 取消。\n")
        try:
            for key, q in QUESTIONS:
                ans = input(f"{key} — {q}\n> ").strip()
                answers[key] = ans
        except (EOFError, KeyboardInterrupt):
            print("\n[提示] 无终端环境请用 --print 打印问题、--answers answers.json 批量生成。")
            sys.exit(1)

    skill_dir = SKILLS_DIR / args.name
    skill_dir.mkdir(parents=True, exist_ok=True)
    out = skill_dir / "SKILL.md"
    if out.exists():
        print(f"⚠️ {out} 已存在，用 --name 换名或手动删除后重跑。")
        sys.exit(3)
    out.write_text(_build_skill(args.name, answers), encoding="utf-8")
    filled = sum(1 for k, _ in QUESTIONS if (answers.get(k) or "").strip())
    print(f"✅ 已生成骨架: {out}（8 问中已填 {filled} 项）")
    print("下一步: python3 ecoskills/meta-audit/scripts/audit.py " + args.name)


if __name__ == "__main__":
    main()
