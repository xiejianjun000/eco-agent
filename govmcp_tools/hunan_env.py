#!/usr/bin/env python3
"""
govmcp_tools/hunan_env.py — 湖南省生态环境厅·环境质量月报工具
====================================================================
数据形态实测结论（2026-08-23）：该栏目无 JSON API——列表是静态分页
（page.js 纯前端翻页），月报正文为 4MB 级静态 HTML，县市区断面/排名数据
直接嵌在页面深处的 <table> 里。故本工具走「列表页定位 → 全文抓取 →
HTML 表格解析」路线，把"附件/深表数据"变成可直接查询的结构化结果。

入口：
  https://sthjt.hunan.gov.cn/sthjt/xxgk/zdly/hjjc/hjzl/index.html
  （2026年N月全省环境质量状况 → /sthjt/xxgk/zdly/hjjc/hjzl/YYYYMM/tYYYYMMDD_*.html）

契约：httpx、30s 超时、正文流式截断 6MB、失败如实报错、绝不编造数据。
"""

from __future__ import annotations

import re
from typing import Any

import httpx
import urllib3

from govmcp.tools.registry import govmcp_tool

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

LIST_URL = "https://sthjt.hunan.gov.cn/sthjt/xxgk/zdly/hjjc/hjzl/index.html"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
MAX_BODY = 6 * 1024 * 1024  # 月报正文可达 4MB+，上限放宽到 6MB
MAX_ROWS = 300

CATEGORY = "环境数据-地方公开数据"
TAGS = ["环境数据", "湖南省", "月报", "断面", "县市区", "公开数据"]


def _client(timeout: float = 30.0) -> httpx.Client:
    return httpx.Client(timeout=timeout, verify=False, headers={"User-Agent": UA})


def _maybe_gunzip(body: bytes, enc: str) -> bytes:
    """按 gzip 魔数判定后再解压（服务端偶发声明 gzip 但未压缩）。"""
    if enc == "gzip" and body[:2] == b"\x1f\x8b":
        import gzip
        return gzip.decompress(body)
    return body


def _fetch(url: str, timeout: float = 30.0) -> str:
    with _client(timeout) as c:
        # 避开 httpx 对大响应 brotli 解码的已知缺陷：只接受 gzip，手动解压
        c.headers["Accept-Encoding"] = "gzip"
        with c.stream("GET", url) as s:
            enc = (s.headers.get("content-encoding") or "").lower()
            body = b""
            for chunk in s.iter_bytes(65536):
                body += chunk
                if len(body) >= MAX_BODY:
                    break
        body = _maybe_gunzip(body, enc)
        return body.decode("utf-8", errors="ignore")


def _strip_tags(s: str) -> str:
    s = re.sub(r"<[^>]+>", "", s)
    return " ".join(s.split())


def _parse_tables(html: str, keyword: str = "") -> tuple[list[list[str]], int]:
    """解析全部 <table>：每个 <tr> 一行、每个 <td>/<th> 一列（已剥标签）。
    keyword 非空时只保留含关键字的行（模糊匹配）；否则返回全部行。"""
    rows: list[list[str]] = []
    for tb in re.findall(r"<table[^>]*>(.*?)</table>", html, re.S):
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", tb, re.S):
            cells = [_strip_tags(c) for c in re.findall(
                r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)]
            cells = [c for c in cells if c]
            if not cells:
                continue
            if keyword and not any(keyword in c for c in cells):
                continue
            rows.append(cells)
            if len(rows) >= MAX_ROWS:
                return rows, len(rows)
    return rows, len(rows)


def _find_article(year: int, month: int) -> tuple[str, str] | None:
    """列表页定位 'YYYY年M月全省环境质量状况' 文章链接（静态 HTML 列表）。
    标题可能在 a 的文本或 title 属性里（本站在 title 属性，正文为图片）。"""
    html = _fetch(LIST_URL, timeout=15.0)
    title = f"{year}年{month}月全省环境质量状况"
    # 主路径：title 属性 + 同标签 href
    for m in re.finditer(r"<a[^>]+title=['\"]\s*" + re.escape(title) +
                         r"\s*['\"][^>]*href=[\"']([^\"']+)[\"']", html):
        url = m.group(1)
        if not url.startswith("http"):
            url = "https://sthjt.hunan.gov.cn" + url
        return url, title
    # 回退：href 在前、title 在后
    for m in re.finditer(r"<a[^>]+href=[\"']([^\"']+)[\"'][^>]+title=['\"]\s*" +
                         re.escape(title) + r"\s*['\"]", html):
        url = m.group(1)
        if not url.startswith("http"):
            url = "https://sthjt.hunan.gov.cn" + url
        return url, title
    # 回退：纯文本标题
    for m in re.finditer(r"<a[^>]+href=[\"']([^\"']+)[\"'][^>]*>\s*" +
                         re.escape(title), html):
        url = m.group(1)
        if not url.startswith("http"):
            url = "https://sthjt.hunan.gov.cn" + url
        return url, title
    return None


@govmcp_tool(
    name="hunan_env_monthly_report",
    description=("湖南省生态环境厅'全省环境质量状况'月报（实测静态HTML,无JSON API）。"
                 "year/month指定年月（如2026/7）；keyword可选（如'冷水江'县市区名或'资江'流域名），"
                 "传关键字只返回含该关键字的表格行，不传返回全部表格行。"
                 "返回：报告链接、断面/排名表格行、数据来源。"),
    category=CATEGORY,
    tags=TAGS,
)
def hunan_env_monthly_report(year: int = 2026, month: int = 7,
                             keyword: str = "") -> dict:
    """湖南省厅环境质量月报：列表定位 → 全文抓取 → 表格解析（关键词过滤）。"""
    try:
        hit = _find_article(int(year), int(month))
        if not hit:
            return {"success": False,
                    "error": f"列表页未找到 {year}年{month}月全省环境质量状况（可能未发布）",
                    "list_url": LIST_URL}
        url, title = hit
        html = _fetch(url)
        rows, total = _parse_tables(html, keyword=keyword.strip())
        return {
            "success": True,
            "title": title,
            "url": url,
            "keyword": keyword.strip(),
            "matched_rows": rows[:MAX_ROWS],
            "matched_count": total,
            "note": ("表格行已剥标签；keyword 为空时返回全部行（上限300）。"
                     "matched_rows 即全量结果——制表/回答时不得省略、合并、改写任何一行，"
                     "行数必须与 matched_count 一致，对不上必须复核原表"
                     if not keyword else
                     "仅含关键字的表格行；matched_rows 即全量结果——制表/回答时"
                     "不得省略、合并、改写任何一行，行数必须与 matched_count 一致"),
            "source": "sthjt.hunan.gov.cn 月报静态 HTML（实测解析）",
        }
    except Exception as e:  # noqa: BLE001
        return {"success": False, "error": f"获取失败: {e}", "list_url": LIST_URL}


_TOOLS: list[Any] = [hunan_env_monthly_report]


def register_hunan_env(reg: Any) -> Any:
    """注册湖南省厅月报工具。"""
    reg.register_batch(_TOOLS)
    return reg


# ─── 聊天通道暴露 ──────────────────────────────────────────────

def _p(props: dict, required: list[str]) -> dict:
    return {"type": "object", "properties": props, "required": required}


CHAT_TOOLS: dict[str, dict] = {
    "hunan_env_monthly_report": {
        "description": ("湖南省生态环境厅全省环境质量状况月报：查某年某月断面水质/县市区数据。"
                        "可传 keyword 过滤（如'冷水江''资江'），返回真实表格行。"),
        "parameters": _p({
            "year": {"type": "integer", "description": "年份，如 2026"},
            "month": {"type": "integer", "description": "月份 1-12，如 7"},
            "keyword": {"type": "string",
                        "description": "可选：县市区名/流域名/断面名模糊过滤，如 冷水江"},
        }, ["year", "month"]),
        "handler": hunan_env_monthly_report,
    },
}

CHAT_NAMES: list[str] = list(CHAT_TOOLS.keys())
