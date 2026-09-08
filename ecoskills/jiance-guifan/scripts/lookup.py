#!/usr/bin/env python3
"""
ecoskills/jiance-guifan/scripts/lookup.py — 生态环境监测技术规范清单检索

用法:
  lookup.py std HJ91.2              按标准号检索（空格/大小写不敏感，支持前缀匹配）
  lookup.py search 地下水            按标准名称关键词检索
  lookup.py medium 水和废水          按环境要素列出全部规范
  lookup.py nav                      要素/监测方式导航与计数
  lookup.py law 生态环境监测条例 31   查附录法规条文（条号支持中文或阿拉伯数字）
  lookup.py lawsearch 弄虚作假        附录法规全文关键词检索
  lookup.py stats                    知识库统计（覆盖面自证）

输出默认 JSON（供工具消费），加 --text 输出人类可读文本。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

KB = Path(__file__).resolve().parent.parent / "kb"

_DIGITS = {"零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
           "六": 6, "七": 7, "八": 8, "九": 9}
_UNITS = {"十": 10, "百": 100, "千": 1000}


def cn2num(s: str) -> int:
    """中文数字转阿拉伯（百位以内足够条号使用）。"""
    s = s.strip()
    if s.isdigit():
        return int(s)
    total, cur = 0, 0
    for ch in s:
        if ch in _DIGITS:
            cur = _DIGITS[ch]
        elif ch in _UNITS:
            total += (cur or 1) * _UNITS[ch]
            cur = 0
        else:
            raise ValueError(f"无法解析的数字: {s}")
    return total + cur


def num2cn(n: int) -> str:
    """阿拉伯转中文条号用数字（1-99）。"""
    if n < 10:
        return "一二三四五六七八九"[n - 1]
    tens, ones = divmod(n, 10)
    return (("" if tens == 1 else "一二三四五六七八九"[tens - 1]) + "十"
            + ("" if ones == 0 else "一二三四五六七八九"[ones - 1]))


def load_catalog() -> list[dict]:
    return json.loads((KB / "监测技术规范清单_结构化.json").read_text(encoding="utf-8"))["items"]


def load_laws() -> list[dict]:
    return json.loads((KB / "监测配套法规全文.json").read_text(encoding="utf-8"))


def norm(s: str) -> str:
    return re.sub(r"[\s　]", "", s or "").upper()


# ---------------------------------------------------------------- commands
def cmd_std(code: str) -> dict:
    key = norm(code)
    items = load_catalog()
    exact = [x for x in items if norm(x["code"]) == key]
    prefix = [x for x in items if norm(x["code"]).startswith(key)] if not exact else []
    hits = exact or prefix
    return {"query": code, "match": "exact" if exact else "prefix",
            "count": len(hits), "results": hits}


def cmd_search(kw: str) -> dict:
    k = norm(kw)
    hits = [x for x in load_catalog() if k in norm(x["name"])]
    return {"query": kw, "count": len(hits), "results": hits}


def cmd_medium(name: str) -> dict:
    k = norm(name)
    hits = [x for x in load_catalog() if k in norm(x["medium"])]
    return {"query": name, "count": len(hits), "results": hits}


def cmd_nav() -> dict:
    items = load_catalog()
    tree: dict[str, dict] = {}
    for x in items:
        node = tree.setdefault(x["medium"], {"count": 0, "sections": {}})
        node["count"] += 1
        node["sections"][x["section"] or "（不分手工/自动）"] = \
            node["sections"].get(x["section"] or "（不分手工/自动）", 0) + 1
    return {"total": len(items), "tree": tree}


def cmd_law(title: str, article: str | None) -> dict:
    docs = load_laws()
    k = norm(title)
    doc = next((d for d in docs if k in norm(d["title"])), None)
    if not doc:
        return {"error": f"未找到法规：{title}",
                "available": [d["title"] for d in docs]}
    if article is None:
        return {"title": doc["title"], "meta": doc["meta"], "pages": doc["pages"],
                "articles": [c["article"] for c in doc["content"] if c["article"]]}
    want = f"第{num2cn(cn2num(re.sub(r'[第条]', '', article)))}条"
    body, hit = [], False
    for c in doc["content"]:
        if c["article"] == want:
            hit = True
            body.append(c["text"])
        elif hit and c["article"]:
            break
        elif hit:
            body.append(c["text"])
    if not hit:
        return {"error": f"{doc['title']} 无 {want}"}
    return {"title": doc["title"], "meta": doc["meta"], "article": want,
            "text": "\n".join(body)}


def cmd_lawsearch(kw: str) -> dict:
    k = norm(kw)
    out = []
    for d in load_laws():
        for c in d["content"]:
            if k in norm(c["text"]):
                out.append({"doc": d["title"], "article": c["article"],
                            "chapter": c["chapter"], "text": c["text"][:400]})
    return {"query": kw, "count": len(out), "results": out}


def cmd_stats() -> dict:
    from collections import Counter
    items = load_catalog()
    laws = load_laws()
    years = [x["year"] for x in items if x["year"]]
    return {
        "标准条目": len(items),
        "按要素": dict(Counter(x["medium"] for x in items).most_common()),
        "按序列": dict(Counter(x["prefix"] or "规范性文件" for x in items).most_common()),
        "强制性国标": sum(1 for x in items if x["mandatory"]),
        "HJ_T旧序列": sum(1 for x in items if x["prefix"] == "HJ/T"),
        "同名多版本": sum(1 for x in items if x.get("same_title_versions")),
        "年份跨度": [min(years), max(years)],
        "附录法规": [{"title": d["title"], "articles": d["articles"]} for d in laws],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="生态环境监测技术规范清单检索")
    ap.add_argument("cmd", choices=["std", "search", "medium", "nav",
                                    "law", "lawsearch", "stats"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--text", action="store_true", help="人类可读输出")
    a = ap.parse_args()

    if a.cmd == "std":
        res = cmd_std(a.args[0])
    elif a.cmd == "search":
        res = cmd_search(a.args[0])
    elif a.cmd == "medium":
        res = cmd_medium(a.args[0])
    elif a.cmd == "nav":
        res = cmd_nav()
    elif a.cmd == "law":
        res = cmd_law(a.args[0], a.args[1] if len(a.args) > 1 else None)
    elif a.cmd == "lawsearch":
        res = cmd_lawsearch(a.args[0])
    else:
        res = cmd_stats()

    if a.text:
        _print_text(a.cmd, res)
    else:
        print(json.dumps(res, ensure_ascii=False, indent=1))
    return 0


def _print_text(cmd: str, res: dict) -> None:
    if "error" in res:
        print("❌", res["error"])
        return
    if cmd in ("std", "search", "medium"):
        print(f"命中 {res['count']} 项：")
        for x in res["results"]:
            flag = "【强制】" if x["mandatory"] else ("【旧序列】" if x["prefix"] == "HJ/T" else "")
            warn = " ⚠️同名多版本" if x.get("same_title_versions") else ""
            print(f"  {x['code']:<20} {x['name']}")
            print(f"      {x['medium']}/{x['section'] or '通用'}｜发布 {x['issued']}"
                  f"｜清单 p{x['source_page']} {flag}{warn}")
    elif cmd == "nav":
        print(f"共 {res['total']} 项")
        for med, node in res["tree"].items():
            print(f"  {med}（{node['count']}）")
            for sec, n in node["sections"].items():
                print(f"      {sec}: {n}")
    elif cmd == "law":
        if "article" in res:
            print(f"《{res['title']}》{res['article']}\n{res['text']}")
        else:
            print(f"《{res['title']}》{res['meta']}\n条文：{len(res['articles'])} 条")
    elif cmd == "lawsearch":
        print(f"命中 {res['count']} 条：")
        for x in res["results"]:
            print(f"  《{x['doc']}》{x['article'] or ''}：{x['text'][:120]}")
    else:
        print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    sys.exit(main())
