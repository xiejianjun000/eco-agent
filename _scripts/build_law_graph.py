#!/usr/bin/env python3
"""
_scripts/build_law_graph.py — 法典引用图谱构建（P1-2 GraphRAG 地基）
==================================================================
解析法典 1242 条全文，提取条文间的"第X条"互引，构建有向边图谱：
  law_graph.json = {count, edges: [[引用方条号, 被引用条号], ...], built_at}

供 statute_related 工具做"违反某条→引用→罚则"多跳（BFS ≤2 跳）。

用法: python3 _scripts/build_law_graph.py
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ecoskills" / "eco-codex" / "scripts"))

from lookup import article, cn2num  # noqa: E402

REF_RE = re.compile(r"第([零一二三四五六七八九十百千]+)条")
TOTAL = 1242
OUT = ROOT / "ecoskills" / "eco-codex" / "kb" / "law_graph.json"


def main() -> None:
    edges: list[list[int]] = []
    failed: list[int] = []
    t0 = time.time()
    for num in range(1, TOTAL + 1):
        try:
            data = article(num)
            text = data.get("text", "")
        except Exception:
            failed.append(num)
            continue
        if not text:
            continue
        for m in REF_RE.finditer(text):
            target = cn2num(m.group(1))
            if 1 <= target <= TOTAL and target != num:
                edges.append([num, target])
        if num % 200 == 0:
            print(f"  进度 {num}/{TOTAL}，已收集 {len(edges)} 条边")
    out = {"count": len(edges), "edges": edges, "built_at": time.strftime("%Y-%m-%d %H:%M:%S"), "failed": failed}
    OUT.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"完成: {len(edges)} 条边，耗时 {time.time() - t0:.1f}s，失败 {len(failed)} 条 → {OUT}")


if __name__ == "__main__":
    main()
