"""站群全文检索工具（湖南政府统一搜索平台，站点 ID 115000000）。"""
from __future__ import annotations

from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .. import config
from ..datasource.http_client import fetch_html

_TYPE_MAP = {
    "all": "news",
    "news": "news",
    "file": "file",
    "site": "site",
    "image": "image",
    "video": "video",
    "service": "service",
    "interact": "interact",
}


def site_search(keyword: str, type: str = "all", page: int = 1) -> list[dict]:
    """在湖南省生态环境厅网站群内做全文检索（省级统一搜索平台）。

    Args:
        keyword: 必填，搜索关键词。
        type: 可选，检索类型 all/news/file/site/image/video/service/interact，默认 all。
        page: 页码，从 1 开始。

    Returns:
        搜索结果列表（标题/类型/发布日期/原文 URL）。
    """
    if not keyword.strip():
        raise ValueError("keyword 为必填参数")
    if len(keyword.strip()) > 100:
        raise ValueError("keyword 过长（最多 100 字）")
    doc_type = _TYPE_MAP.get(type, "news")
    # 搜索平台以 ?q= 传参，结果 HTML 中带分页参数 page=2
    url = f"{config.SEARCH_URL}/{config.SITE_ID}/{doc_type}"
    html = fetch_html(
        url,
        params={"q": keyword.strip(), "sm": "0", "timetype": "timeqb", "page": page},
    )
    soup = BeautifulSoup(html, "html.parser")
    results: list[dict] = []
    for li in soup.select("ul.result-list li, ul.search-list li, .search-item"):
        a = li.find("a", href=True)
        if not a:
            continue
        text = li.get_text(" ", strip=True)
        results.append(
            {
                "title": a.get_text(" ", strip=True),
                "url": urljoin(config.SEARCH_URL, a["href"]),
                "date": _extract_date(text),
            }
        )
    # 兜底：直接收集含链接的列表项
    if not results:
        for a in soup.find_all("a", href=True):
            href = urljoin(config.SEARCH_URL, a["href"])
            if "hunan.gov.cn" not in href or href.startswith(config.SEARCH_URL):
                continue
            title = a.get_text(" ", strip=True)
            if title:
                results.append({"title": title, "url": href, "date": ""})
    return results[:20]


def _extract_date(text: str) -> str:
    import re

    m = re.search(r"\d{4}-\d{2}-\d{2}", text)
    return m.group(0) if m else ""
