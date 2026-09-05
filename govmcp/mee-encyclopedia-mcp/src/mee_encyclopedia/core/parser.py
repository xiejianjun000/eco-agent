"""HTML / 链接 / 表格解析工具。"""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup


def parse_links(html: str, base_url: str, limit: int = 50) -> list[dict[str, str]]:
    """解析页面中所有链接，返回 [{title, url}]（仅 http/https）。"""
    soup = BeautifulSoup(html, "lxml")
    items: list[dict[str, str]] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        title = a.get_text(strip=True)
        if not href or href.startswith(("javascript:", "#", "mailto:")):
            continue
        full = urljoin(base_url, href)
        parsed = urlparse(full)
        if parsed.scheme not in ("http", "https"):
            continue
        if full in seen:
            continue
        seen.add(full)
        items.append({"title": title or full, "url": full})
        if len(items) >= limit:
            break
    return items


def parse_table(html: str, limit: int = 30) -> list[list[str]]:
    """解析页面中第一个表格，返回行列文本矩阵。"""
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table")
    if not table:
        return []
    rows: list[list[str]] = []
    for tr in table.find_all("tr"):
        cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
        if any(cells):
            rows.append(cells)
        if len(rows) >= limit:
            break
    return rows


def parse_article(html: str, max_chars: int = 8000) -> str:
    """提取正文文本（优先 <article>，否则取 body 文本并压缩空白）。"""
    soup = BeautifulSoup(html, "lxml")
    node = (
        soup.find("article")
        or soup.find("div", class_=re.compile("(TRS_Editor|Custom_UnionStyle|content|article|main)"))
        or soup.body
        or soup
    )
    text = node.get_text(separator="\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text[:max_chars]


def extract_json_from_script(html: str, pattern: str = r"window\._DATA_\s*=\s*(\{.*?\});") -> str | None:
    """尝试从内联脚本中提取 JSON 片段（兼容性工具）。"""
    m = re.search(pattern, html, re.S)
    return m.group(1) if m else None


def safe_filename(name: str) -> str:
    """清洗文件名，去掉路径分隔符与非法字符。"""
    name = re.sub(r'[\\/:*?"<>|\r\n]+', "_", name).strip()
    return name[:120] or "download"
