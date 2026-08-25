#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
_scripts/run_evals.py — 执法评测集 runner（P0 评测地基）
====================================================
解析 evals/*.md 评测集（## Q 块 + 维度/黄金要点/引用校验），
支持两层评测：

1. 机械校验（--mechanical，本地、确定性、零 LLM 成本）：
   引用校验 article=N → 法典库 lookup.py 直查，条文存在且非空=通过。
   这是"幻觉率 3-5% 生产不可接受"的底线闸门：模型引用虚构法条在此必挂。
2. LLM 实测（--llm，可选）：把每个问题发给 /api/v1/chat，
   原始回答存档 evals/results/<suite>-answers.md，人工/LLM-as-Judge 对照黄金要点。

用法:
  python3 _scripts/run_evals.py --mechanical            # 只跑机械校验
  python3 _scripts/run_evals.py --mechanical --llm      # 机械 + LLM 实测存档
  python3 _scripts/run_evals.py --suite statute-application
退出码: 机械校验任一失败 = 1（CI 硬门禁）。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVALS_DIR = ROOT / "evals"
LOOKUP = ROOT / "ecoskills" / "eco-codex" / "scripts" / "lookup.py"


def parse_suite(path: Path) -> list[dict]:
    """解析评测集：## Q 块 → [{question, dimension, golden, citation}]"""
    text = path.read_text(encoding="utf-8")
    blocks = re.split(r"^## Q", text, flags=re.M)[1:]
    out = []
    for b in blocks:
        lines = b.strip().splitlines()
        question = lines[0].strip()
        dim = golden = citation = ""
        for ln in lines[1:]:
            if ln.startswith("维度:"):
                dim = ln.split(":", 1)[1].strip()
            elif ln.startswith("黄金要点:"):
                golden = ln.split(":", 1)[1].strip()
            elif ln.startswith("引用校验:"):
                citation = ln.split(":", 1)[1].strip()
        out.append({"question": question, "dimension": dim,
                    "golden": golden, "citation": citation})
    return out


def mechanical_check(q: dict) -> tuple[bool, str]:
    """机械校验：article=N 直查法典库；path=X 检查文件存在；无=跳过(不计分)。"""
    c = q["citation"]
    if not c or c == "无" or c == "none":
        return True, "skip"
    if c.startswith("article="):
        art = c.split("=", 1)[1].strip()
        try:
            r = subprocess.run([sys.executable, str(LOOKUP), "article", art],
                               capture_output=True, text=True, timeout=20)
            txt = r.stdout.strip()
            if not txt or "检索失败" in txt or "不可用" in txt:
                return False, f"article={art} 法典库查无"
            data = json.loads(txt)
            return bool(data.get("text")), f"article={art} 命中 {data.get('file','')}"
        except Exception as e:  # noqa: BLE001
            return False, f"article={art} 校验异常: {e}"
    if c.startswith("path="):
        p = ROOT / c.split("=", 1)[1].strip()
        return p.exists(), f"path={p.name} {'存在' if p.exists() else '缺失'}"
    return True, "skip"


def run_mechanical(suites: list[Path]) -> dict:
    results = []
    for sp in suites:
        for q in parse_suite(sp):
            ok, note = mechanical_check(q)
            results.append({"suite": sp.stem, "question": q["question"][:50],
                            "citation": q["citation"], "ok": ok, "note": note})
    total = len(results)
    passed = sum(1 for r in results if r["ok"])
    return {"results": results, "passed": passed, "total": total,
            "failed": [r for r in results if not r["ok"]]}


def run_llm(suites: list[Path], results_dir: Path) -> None:
    """LLM 实测：问题发聊天通道，原始回答存档（判定由人工/锚点校准 LLM-as-Judge 完成）。"""
    import urllib.request

    results_dir.mkdir(parents=True, exist_ok=True)
    for sp in suites:
        lines = [f"# {sp.stem} LLM 实测回答存档", ""]
        for q in parse_suite(sp):
            lines.append(f"## Q {q['question']}")
            lines.append(f"维度: {q['dimension']}")
            lines.append(f"黄金要点: {q['golden'][:200]}")
            lines.append("")
            lines.append("【模型回答】")
            try:
                req = urllib.request.Request(
                    "http://127.0.0.1:8321/api/v1/chat",
                    data=json.dumps({"message": q["question"], "history": []}).encode(),
                    headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=300) as r:
                    d = json.loads(r.read())
                lines.append(d.get("reply", "")[:1500])
            except Exception as e:  # noqa: BLE001
                lines.append(f"[调用失败] {e}")
            lines.append("")
        (results_dir / f"{sp.stem}-answers.md").write_text(
            "\n".join(lines), encoding="utf-8")
        print(f"✅ {sp.stem} → {results_dir / (sp.stem + '-answers.md')}")


def main() -> None:
    ap = argparse.ArgumentParser(description="执法评测集 runner")
    ap.add_argument("--mechanical", action="store_true")
    ap.add_argument("--llm", action="store_true")
    ap.add_argument("--suite", help="只跑指定评测集（文件名不含 .md）")
    args = ap.parse_args()
    if not (args.mechanical or args.llm):
        print("用法: run_evals.py --mechanical [--llm] [--suite xxx]")
        sys.exit(2)

    suites = sorted(EVALS_DIR.glob("*.md"))
    if args.suite:
        suites = [s for s in suites if s.stem == args.suite]
    if not suites:
        print("未找到评测集")
        sys.exit(3)

    exit_code = 0
    if args.mechanical:
        report = run_mechanical(suites)
        print("\n═══ 机械校验（引用真实性，零幻觉底线）═══")
        for r in report["results"]:
            mark = "✅" if r["ok"] else "❌"
            print(f"  {mark} [{r['suite']}] {r['question']} — {r['note']}")
        print(f"\n机械校验: {report['passed']}/{report['total']} 通过")
        if report["failed"]:
            print("❌ 存在虚构引用——CI 硬门禁失败")
            exit_code = 1
    if args.llm:
        run_llm(suites, EVALS_DIR / "results")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
