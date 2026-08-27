"""排污许可领域：排污许可信息查询、系统入口。"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

PERMIT_PLATFORM = "https://permit.mee.gov.cn/"


def search_permit(fetcher, cache, company: str) -> dict:
    """查询企业排污许可证信息（许可证号/有效期/排污类别）。来源：全国排污许可证管理信息平台。"""
    key = f"permit:search:{company}"
    cached = cache.get(key)
    if cached:
        return {**cached, "cache": "hit"}
    result = {"company": company, "source": PERMIT_PLATFORM, "items": [], "note": ""}
    try:
        html = fetcher.get_text(PERMIT_PLATFORM)
        from ..core.parser import parse_article
        text = parse_article(html, max_chars=2000)
        result["page_snippet"] = text[:1000] if text else ""
        result["note"] = "排污许可平台为业务系统（需登录/验证码），公开端不支持结构化查询；建议派发 browser-agent 带登录态查询"
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)
    cache.set(key, result, ttl=600)
    return result


def permit_guide() -> dict:
    """排污许可知识导览（百科知识域）。"""
    return {
        "source": PERMIT_PLATFORM,
        "guide": [
            "排污许可制度：固定污染源排污许可分类管理名录",
            "排污许可证：正本（基本信息）+ 副本（许可事项）",
            "管理类别：重点管理 / 简化管理 / 登记管理",
            "查询入口：全国排污许可证管理信息平台公开端",
        ],
    }
