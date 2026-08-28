#!/usr/bin/env python3
"""
ecoskills/meta-test/scripts/test.py — 技能自测用例生成（auto-test 元技能）
=========================================================================
从 SKILL.md 的决策表/时限/Step 自动生成测试用例集，落盘 evals/<name>-cases.md。
只从技能原文出题（不编造），每条含 维度/黄金要点/引用校验。

用法:
  python3 ecoskills/meta-test/scripts/test.py <技能名> [--out PATH]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent
SKILLS_DIR = ROOT / "ecoskills"
EVALS_DIR = ROOT / "evals"


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


def _table_rows(body: str) -> list[list[str]]:
    """解析 markdown 表格的数据行（跳过表头与分隔行）。"""
    rows: list[list[str]] = []
    for line in body.splitlines():
        if line.strip().startswith("|") and "---" not in line:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            rows.append(cells)
    # 跳过表头行（通常第一行）
    data = [r for i, r in enumerate(rows) if i != 0 or not any(
        c.endswith(("要点", "适用", "项", "情节", "审查项")) for c in r)]
    if data:
        # 若第一行疑似表头（所有单元格短且无数字），剔除
        first = data[0]
        if all(len(c) <= 8 and not re.search(r"\d", c) for c in first) and len(data) > 1:
            data = data[1:]
    return data


def _numbers(text: str) -> list[str]:
    """抽取时限/数字类事实（如 '5 日内申请'、'60 日内'、'1 万-100 万'）。"""
    return re.findall(r"\d+(?:[\.\d]*-)?\d*\s*(?:日|天|小时|年|个月|万|倍|%|条|类|步)", text)


def generate_cases(name: str) -> dict:
    md = SKILLS_DIR / name / "SKILL.md"
    if not md.exists():
        print(f"❌ 技能不存在: {name}")
        sys.exit(2)
    meta, body = _parse_frontmatter(md.read_text(encoding="utf-8"))
    desc = meta.get("description", "")
    lines: list[str] = [f"# {name} 技能自测用例（由 meta-test 自动生成）", ""]

    # ① 知识题：从决策表出题
    tables = _table_rows(body)
    for t in tables:
        if len(t) >= 2 and len(t[0]) <= 12:
            lines.append(f"## Q 知识题: 在《{name}》技能中，「{t[0]}」对应的要点是什么？")
            lines.append("维度: 知识记忆")
            lines.append(f"黄金要点: {t[1]}")
            lines.append("引用校验: 无")
            lines.append("")

    # ② 知识题：数字/时限
    for num in _numbers(body)[:5]:
        lines.append(f"## Q 知识题: {name} 技能涉及的时限/数值「{num}」的具体规定是什么？")
        lines.append("维度: 知识记忆")
        lines.append("黄金要点: 与技能原文一致（见 SKILL.md 相关表格）")
        lines.append("引用校验: 无")
        lines.append("")

    # ③ 应用场景题：触发词 + 流程
    triggers = re.findall(r"触发词[:：]([^\n]+)", desc)
    for tg in (triggers or [desc[:30]])[:3]:
        lines.append(f"## Q 应用题: 用户提出「{tg.strip()}」类问题，模型应执行什么流程、输出什么格式？")
        lines.append("维度: 流程遵循")
        lines.append(f"黄金要点: 按 {name} 技能 Step 流程执行；输出符合技能规定的格式；涉处罚时含免责与[待确认]标注")
        lines.append("引用校验: 无")
        lines.append("")

    # ④ 机械校验项：正文引用的条文（如 第164条/第1108条 形式）
    articles = re.findall(r"第\s*\d+\s*条|第\s*[零一二三四五六七八九十百千]+\s*条", body)
    for art in sorted(set(articles))[:8]:
        art_num = re.sub(r"[^\d]", "", art)
        lines.append(f"## Q 机械校验: 《{name}》技能引用的「{art}」是否存在于法典库？")
        lines.append("维度: 引用真实性")
        lines.append(f"黄金要点: lookup.py article 查询「{art}」返回原文")
        lines.append(f"引用校验: article={art_num}")
        lines.append("")

    lines.append("> 本文件由 meta-test 自动生成；黄金要点供 LLM-as-Judge 对照，机械校验项本地即可验证。")

    out_path = EVALS_DIR / f"{name}-cases.md"
    EVALS_DIR.mkdir(exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return {"skill": name, "out": str(out_path),
            "cases": sum(1 for l in lines if l.startswith("## Q"))}


def main() -> None:
    ap = argparse.ArgumentParser(description="eco-agent 技能自测用例生成")
    ap.add_argument("skill", help="技能名")
    args = ap.parse_args()
    result = generate_cases(args.skill)
    print(f"✅ {result['skill']} → {result['out']}（{result['cases']} 条用例）")


if __name__ == "__main__":
    main()
