"""读取工具族：网页正文、栏目列表、站点链接、全站搜索。"""
from __future__ import annotations

import logging
from typing import Optional

from .fetcher import Fetcher
from .parser import parse_article, parse_links

logger = logging.getLogger(__name__)


class Reader:
    """通用读取能力，供各领域模块复用。"""

    def __init__(self, fetcher: Fetcher) -> None:
        self._fetcher = fetcher

    def read_page(self, url: str, max_chars: int = 8000) -> dict:
        """读取任意公开网页正文。"""
        html = self._fetcher.get_text(url)
        text = parse_article(html, max_chars=max_chars)
        return {"url": url, "title": _extract_title(html), "content": text, "source": "mee_web"}

    def list_links(self, url: str, limit: int = 50) -> dict:
        """列出页面中的公开链接（用于探索栏目结构）。"""
        html = self._fetcher.get_text(url)
        links = parse_links(html, base_url=url, limit=limit)
        return {"url": url, "count": len(links), "links": links}

    def search_site(self, keyword: str, base: str = "https://www.mee.gov.cn") -> dict:
        """基于站点地图/首页链接做关键词粗筛（无官方站内搜索 API 时的兜底）。"""
        try:
            html = self._fetcher.get_text(base)
            links = parse_links(html, base_url=base, limit=200)
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc), "matches": []}
        hits = [lk for lk in links if keyword in lk["title"]]
        return {"keyword": keyword, "count": len(hits), "matches": hits[:20]}


def _extract_title(html: str) -> str:
    import re

    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    return m.group(1).strip() if m else ""
