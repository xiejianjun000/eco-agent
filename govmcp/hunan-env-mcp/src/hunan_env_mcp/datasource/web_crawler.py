"""政务栏目列表/详情爬虫（双模式）。

实测（2026-08-27）：
- list_tyxx 模板（新闻/通知类）：列表由 JS 动态加载，数据源为湖南政务统一检索接口
    POST https://api.hunan.gov.cn/search/common/search/{channelId}
- index / list_sy3 / list_xzgsx 模板（公示/政策类）：服务端静态 HTML
    分页 {template}.html → {template}_2.html → ...
- 详情页：t{YYYYMMDD}_{id}.html；附件：files/{md5}.pdf|xlsx|doc
"""
from __future__ import annotations

import datetime as _dt
import json
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests

from .. import config
from .http_client import USER_AGENT, _limiter, fetch_html

_DETAIL_RE = re.compile(config.DETAIL_RE_PATTERN)
_ATTACH_RE = re.compile(config.ATTACH_RE_PATTERN)
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_DATETIME_RE = re.compile(r"\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}")

# 统一检索接口请求体（与 list_all.js 保持一致）
_API_PAYLOAD = {
    "datas": [
        {"key": "status", "value": "4", "join": "and", "queryType": "term"},
        {"key": "publishedTime", "sort": "true", "order": "desc", "queryType": "term"},
    ],
    "page": 1,
    "_pageSize": 20,
    "_isAgg": "true",
}


def _extract_date(text: str) -> str:
    m = _DATETIME_RE.search(text) or _DATE_RE.search(text)
    return m.group(0) if m else ""


def _ts_to_date(ts: int) -> str:
    try:
        return _dt.datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d")
    except (ValueError, OSError):
        return ""


# ---------- API 模式（list_tyxx 模板） ----------

def _list_api(api_ids: list[int], page: int) -> list[dict]:
    items: list[dict] = []
    for cid in api_ids:
        _limiter.wait()
        resp = curl_requests.post(
            f"{config.SEARCH_API}/{cid}",
            json={**_API_PAYLOAD, "page": page},
            headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"},
            impersonate="chrome",
            timeout=config.REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = json.loads(resp.text)
        results = (data.get("data") or {}).get("results") or []
        for r in results:
            url = r.get("url") or ""
            if url and not url.startswith("http"):
                url = urljoin(config.BASE_URL, url)
            items.append(
                {
                    "title": r.get("title", ""),
                    "url": url,
                    "date": _ts_to_date(r.get("publishedTime") or r.get("pubTime") or 0),
                }
            )
    return items


# ---------- HTML 模式（index / list_sy3 / list_xzgsx 模板） ----------

def _list_html(channel_path: str, template: str, page: int, detail_pattern: str | None = None) -> list[dict]:
    tpl = template or "index"
    filename = f"{tpl}.html" if page <= 1 else f"{tpl}_{page}.html"
    url = f"{config.BASE_URL}/sthjt/{channel_path.strip('/')}/{filename}"
    detail_re = re.compile(detail_pattern) if detail_pattern else _DETAIL_RE
    try:
        html = fetch_html(url)
    except Exception:
        # 越界/空白页宽容语义：栏目内容不足分页数时返回空列表
        return []
    soup = BeautifulSoup(html, "html.parser")
    items: list[dict] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = urljoin(config.BASE_URL + "/", a["href"])
        if not detail_re.search(href):
            continue
        title = a.get_text(" ", strip=True)
        if not title:
            continue
        if href in seen:
            continue
        seen.add(href)
        li = a.find_parent("li") or a.find_parent("dd") or a.find_parent("tr") or a
        date = _extract_date(li.get_text(" ", strip=True))
        items.append({"title": title, "url": href, "date": date})
    return items


# ---------- 统一入口 ----------

def list_articles(channel_key: str, page: int = 1) -> list[dict]:
    """按栏目配置抓取列表页，返回 [{title, url, date}]。"""
    channel = config.CHANNELS[channel_key]
    if channel["mode"] == "api":
        return _list_api(channel["api_ids"], max(page, 1))
    return _list_html(
        channel["path"],
        channel.get("template", "index"),
        max(page, 1),
        detail_pattern=channel.get("detail_pattern"),
    )


# ---------- 详情页 ----------

def get_detail(detail_url: str) -> dict:
    """解析详情页：标题 / 发布机构 / 日期 / 正文 / 附件列表。"""
    html = fetch_html(detail_url)
    soup = BeautifulSoup(html, "html.parser")
    title_node = soup.find("h1") or soup.select_one(".article-title, .tit, h2")
    title = title_node.get_text(" ", strip=True) if title_node else ""

    body_node = (
        soup.select_one(".article-content, .content, .TRS_Editor, .article") or soup.find("body")
    )
    body = body_node.get_text("\n", strip=True) if body_node else ""

    page_text = soup.get_text(" ", strip=True)
    date = _extract_date(page_text)
    source = ""
    m = re.search(r"(?:发布机构|来源)[:：]\s*([^\s|｜]+)", page_text)
    if m:
        source = m.group(1)

    attachments: list[dict] = []
    for a in soup.find_all("a", href=True):
        href = urljoin(config.BASE_URL + "/", a["href"])
        if _ATTACH_RE.search(href):
            attachments.append(
                {"name": a.get_text(" ", strip=True) or href.rsplit("/", 1)[-1], "url": href}
            )
    return {
        "title": title,
        "source": source,
        "date": date,
        "url": detail_url,
        "content": body[:20000],
        "attachments": attachments,
    }
