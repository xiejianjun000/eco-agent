#!/usr/bin/env python3
"""
ecoskills/eco-codex/scripts/lookup.py — 生态环境法典条文检索

用法:
  lookup.py article 1054          按条号精确检索（支持"第一千零五十四条"）
  lookup.py search 逃避监管        关键词检索（返回命中条文全文）
  lookup.py nav                    编章导航树
  lookup.py bian 5                 指定编的章节概览

输出为 JSON（供工具/程序消费）或 --text 人类可读。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

KB = Path(__file__).resolve().parent.parent / "kb"

_DIGITS = {"零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_UNITS = {"十": 10, "百": 100, "千": 1000, "万": 10000}
_BIAN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5}


def cn2num(s: str) -> int:
    """中文数字转阿拉伯（支持千位以内 + 万）。"""
    if s.isdigit():
        return int(s)
    total, cur = 0, 0
    for ch in s:
        if ch in _DIGITS:
            cur = _DIGITS[ch]
        elif ch in _UNITS:
            unit = _UNITS[ch]
            total += (cur or 1) * unit
            cur = 0
        else:
            raise ValueError(f"无法解析的数字: {s}")
    return total + cur


def parse_article_ref(ref: str) -> int:
    """解析条号引用：'1054' / '第一千零五十四条' / '第1054条' -> 1054"""
    m = re.search(r"第([一二三四五六七八九十百千万零\d]+)条", ref)
    if m:
        return cn2num(m.group(1))
    return cn2num(ref)


def _load_index() -> dict:
    return json.loads((KB / "index.json").read_text(encoding="utf-8"))


def _article_files() -> list[Path]:
    return sorted(KB.glob("第*编_*.md"))


def article(article_num: int) -> dict:
    """按条号精确检索，返回 {num, text, file}。"""
    files = _article_files()
    pattern = re.compile(r"^第([一二三四五六七八九十百千万零\d]+)条\s*(.*)$", re.M)
    for f in files:
        content = f.read_text(encoding="utf-8")
        for m in pattern.finditer(content):
            if cn2num(m.group(1)) == article_num:
                return {"num": article_num, "text": f"第{m.group(1)}条　{m.group(2)}", "file": f.name}
    return {"num": article_num, "text": None, "error": f"未找到第{article_num}条"}


def search(keyword: str, limit: int = 12) -> dict:
    """关键词检索：命中条文全文 + 所在编文件。
    单次返回有截断（达到 limit 即止），truncated=True 表示可能还有未返回的命中；
    精确条号请用 article 直查。"""
    hits = []
    pattern = re.compile(r"^第[一二三四五六七八九十百千万零\d]+条[^\n]*", re.M)
    for f in _article_files():
        content = f.read_text(encoding="utf-8")
        for m in pattern.finditer(content):
            if keyword in m.group(0):
                hits.append({"text": m.group(0)[:400], "file": f.name})
                if len(hits) >= limit:
                    return {"keyword": keyword, "count": len(hits), "hits": hits, "truncated": True}
    return {"keyword": keyword, "count": len(hits), "hits": hits, "truncated": False}


def nav() -> dict:
    """五编章结构导航。"""
    bian_re = re.compile(r"^第([一二三四五六七八九十]+)编\s*(.+)$", re.M)
    zhang_re = re.compile(r"^第([一二三四五六七八九十百]+)章\s*(.+)$", re.M)
    out = []
    for f in _article_files():
        content = f.read_text(encoding="utf-8")
        bm = bian_re.search(content)
        if not bm:
            continue
        chapters = [m.group(2).strip() for m in zhang_re.finditer(content)]
        out.append({"num": _BIAN_NUM.get(bm.group(1), 0), "name": bm.group(2).strip(),
                    "chapters": chapters})
    return {"bians": out}


def bian_overview(bian_num: int) -> dict:
    """指定编概览：章节 + 条文区间。"""
    files = {int(f.name[1]): f for f in _article_files() if f.name.startswith("第")}
    f = files.get(bian_num)
    if f is None:
        return {"error": f"编不存在: {bian_num}"}
    content = f.read_text(encoding="utf-8")
    zhang_re = re.compile(r"^第([一二三四五六七八九十百]+)章\s*(.+)$", re.M)
    tiao_re = re.compile(r"^第([一二三四五六七八九十百千万零\d]+)条\s*(.*)$", re.M)
    nums = [cn2num(m.group(1)) for m in tiao_re.finditer(content)]
    return {
        "bian": bian_num,
        "file": f.name,
        "chapters": [m.group(2).strip() for m in zhang_re.finditer(content)],
        "article_range": [min(nums), max(nums)] if nums else [],
        "article_count": len(nums),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="生态环境法典条文检索")
    parser.add_argument("command", choices=["article", "search", "nav", "bian"])
    parser.add_argument("arg", nargs="?", default="")
    parser.add_argument("--text", action="store_true", help="人类可读输出")
    args = parser.parse_args()

    if args.command == "article":
        try:
            result = article(parse_article_ref(args.arg))
        except ValueError as e:
            result = {"error": str(e)}
    elif args.command == "search":
        result = search(args.arg)
    elif args.command == "nav":
        result = nav()
    else:
        result = bian_overview(int(args.arg))

    if args.text:
        if args.command == "article":
            print(result.get("text") or result.get("error"))
        elif args.command == "search":
            for h in result["hits"]:
                print(f"[{h['file']}] {h['text'][:120]}")
            print(f"共 {result['count']} 条命中")
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
