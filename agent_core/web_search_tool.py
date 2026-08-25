#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
agent_core/web_search_tool.py — 网页搜索工具（多引擎兜底，无 API key）
====================================================================
补齐 eco-agent 的信息获取缺口：从关键词发现 URL（web_fetch 只"读"不"搜"）。

引擎顺序：Bing → DuckDuckGo Lite → Sogou，任一成功即返回；
全部失败返回权威源指引（法规/政策检索直通车）。
返回 top 结果 {title, url} 列表，模型随后用 web_fetch 抓正文
（web_fetch 仍受域名白名单约束——搜索只负责"发现"，抓取负责"契约"）。
"""

from __future__ import annotations

import html
import json
import re
import urllib.parse
import urllib.request

TIMEOUT = 12
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

_FALLBACK_GUIDE = (
    "所有搜索引擎均不可达。权威源直通车（web_fetch 白名单内）：\n"
    "- 法规/政策全文: gov.cn 政策文件库 https://sousuo.www.gov.cn/ 或 "
    "https://flk.npc.gov.cn/（国家法律法规数据库）\n"
    "- 生态环境部: https://www.mee.gov.cn/ 站内检索\n"
    "- 行政法规库: https://xzfg.moj.gov.cn/\n"
    "可先抓这些站点首页/栏目页再定位全文页。"
)


def _fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept-Language": "zh-CN,zh;q=0.9"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read().decode("utf-8", errors="replace")


def _parse_links(page: str, patterns: list[tuple[str, str]]) -> list[dict]:
    """按 (链接正则, 标题正则) 提取结果。"""
    out: list[dict] = []
    for href_re, title_re in patterns:
        hrefs = re.findall(href_re, page)
        titles = re.findall(title_re, page)
        for h, t in zip(hrefs, titles):
            h = html.unescape(h)
            t = html.unescape(re.sub(r"<[^>]+>", "", t)).strip()
            if t and h.startswith("http"):
                out.append({"title": t[:120], "url": h[:300]})
            if len(out) >= 8:
                return out[:8]
    return out[:8]


def search_bing(query: str) -> list[dict]:
    q = urllib.parse.quote(query)
    page = _fetch(f"https://www.bing.com/search?q={q}&setlang=zh-CN&count=10")
    return _parse_links(page, [
        (r'<h2><a href="([^"]+)"', r'<h2><a[^>]*>(.*?)</a></h2>'),
    ])


def search_ddg(query: str) -> list[dict]:
    q = urllib.parse.quote(query)
    page = _fetch(f"https://lite.duckduckgo.com/lite/?q={q}")
    return _parse_links(page, [
        (r'<a rel="nofollow" href="([^"]+)"', r'<a rel="nofollow"[^>]*>(.*?)</a>'),
    ])


def search_sogou(query: str) -> list[dict]:
    q = urllib.parse.quote(query)
    page = _fetch(f"https://www.sogou.com/web?query={q}")
    return _parse_links(page, [
        (r'href="([^"]+)"[^>]*id="sogou_vr_[^"]*"', r'<h3[^>]*>.*?<a[^>]*>(.*?)</a>'),
    ])


def web_search(query: str, limit: int = 5) -> str:
    """搜索网页。返回 JSON 字符串 {ok, engine, results, note}。"""
    q = (query or "").strip()
    if not q:
        return json.dumps({"ok": False, "error": "空查询"}, ensure_ascii=False)
    for engine, fn in (("bing", search_bing), ("duckduckgo", search_ddg),
                       ("sogou", search_sogou)):
        try:
            results = fn(q)
            if results:
                return json.dumps({
                    "ok": True, "engine": engine,
                    "count": min(len(results), limit), "results": results[:limit],
                    "note": "用 web_fetch 抓取白名单内结果页正文；非白名单域名会失败",
                }, ensure_ascii=False)
        except Exception:
            continue
    return json.dumps({"ok": False, "engine": "none",
                       "error": _FALLBACK_GUIDE}, ensure_ascii=False)
