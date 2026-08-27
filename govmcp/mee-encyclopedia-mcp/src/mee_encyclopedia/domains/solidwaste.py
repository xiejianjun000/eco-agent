"""固废危废领域：危废名录查询、固废系统入口。"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

SOLID_WASTE = "https://www.cswm.org.cn/"
CHEMICAL_PLATFORM = "http://gfxt.meescc.cn"


def search_waste_category(fetcher, cache, keyword: str) -> dict:
    """查询危险废物类别信息（废物类别/代码/危险特性）。来源：国家危险废物名录（2025 版）等。"""
    key = f"waste:category:{keyword}"
    cached = cache.get(key)
    if cached:
        return {**cached, "cache": "hit"}
    result = {"keyword": keyword, "source": SOLID_WASTE, "items": [], "note": ""}
    try:
        html = fetcher.get_text(SOLID_WASTE)
        from ..core.parser import parse_article, parse_links
        links = parse_links(html, base_url=SOLID_WASTE, limit=100)
        items = [lk for lk in links if keyword in lk["title"]][:10]
        result["items"] = items
        result["note"] = "危废名录详细分类表可下载官方名录文件；若未命中请使用 download_file 获取名录 PDF/Excel"
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)
    cache.set(key, result, ttl=3600, slow=True)
    return result


def list_waste_entrances() -> dict:
    """固废危废相关系统入口（百科知识域）。"""
    return {
        "固废化学品管理信息系统": SOLID_WASTE,
        "全国固体废物管理信息系统": "http://gf.mee.gov.cn",
        "新化学物质登记平台": CHEMICAL_PLATFORM,
        "废弃电器电子产品处理信息": "https://www.meescc.cn",
    }
