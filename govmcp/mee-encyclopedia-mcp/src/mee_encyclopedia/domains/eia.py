"""环评领域：环评信用、登记表备案、环评机构信息。"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

EIA_CREDIT = "https://xypt.china-eia.com/XYPT/"
EIA_RECORD = "https://beian.china-eia.com/"


def query_eia_credit(fetcher, cache, name: str) -> dict:
    """查询环评机构信用信息（单位名称/信用等级/处罚记录）。来源：环评信用平台。"""
    key = f"eia:credit:{name}"
    cached = cache.get(key)
    if cached:
        return {**cached, "cache": "hit"}
    result = {"query": name, "source": EIA_CREDIT, "items": [], "note": ""}
    try:
        html = fetcher.get_text(EIA_CREDIT)
        from ..core.parser import parse_article
        text = parse_article(html, max_chars=2000)
        result["page_snippet"] = text[:1000] if text else ""
        result["note"] = "环评信用平台为登录后动态查询系统，公开页面无法直接结构化查询；需登录态（可派发 browser-agent 处理）"
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)
    cache.set(key, result, ttl=600)
    return result


def list_eia_entrances() -> dict:
    """列出环评相关业务系统入口（百科知识域：环评导览）。"""
    return {
        "全国环评信用平台": EIA_CREDIT,
        "环境影响评价登记表备案系统": EIA_RECORD,
        "环评工程师注册系统": "http://www.china-eia.com",
        "来源": "https://www.china-eia.com",
    }
