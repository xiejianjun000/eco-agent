"""水环境领域：地表水水质、海水水质、流域监管。"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

SURFACE_WATER = "https://szzdjc.cnemc.cn:8070/GJZ/Business/Publish/Main.html"
SEA_WATER = "http://ep.nmemc.org.cn:8888/Water/"


def read_surface_water(fetcher, cache, station: Optional[str] = None) -> dict:
    """读取国家地表水水质自动监测数据（每 4 小时更新）。"""
    key = f"water:surface:{station or 'all'}"
    cached = cache.get(key)
    if cached:
        return {**cached, "cache": "hit"}
    result = {"station": station or "全国断面", "source": SURFACE_WATER, "content": "", "note": ""}
    try:
        html = fetcher.get_text(SURFACE_WATER)
        from ..core.parser import parse_article, parse_table
        table = parse_table(html, limit=20)
        if table:
            result["table"] = table
        text = parse_article(html, max_chars=3000)
        if text:
            result["content"] = text
        else:
            result["note"] = "实时发布系统为动态页面，未解析到表格；建议升级 Playwright 浏览器抓取"
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)
    cache.set(key, result, ttl=600)
    return result


def read_sea_water(fetcher, cache, region: Optional[str] = None) -> dict:
    """读取国家海水水质监测数据。来源：国家海洋环境监测中心。"""
    key = f"water:sea:{region or 'all'}"
    cached = cache.get(key)
    if cached:
        return {**cached, "cache": "hit"}
    result = {"region": region or "全国", "source": SEA_WATER, "content": "", "note": ""}
    try:
        html = fetcher.get_text(SEA_WATER)
        from ..core.parser import parse_article, parse_table
        table = parse_table(html, limit=20)
        if table:
            result["table"] = table
        text = parse_article(html, max_chars=3000)
        if text:
            result["content"] = text
        else:
            result["note"] = "海水水质发布页为动态页面，未解析到数据；建议升级浏览器抓取"
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)
    cache.set(key, result, ttl=600)
    return result


def list_river_bureaus() -> dict:
    """列出七大流域海域生态环境监督管理局（百科知识域：流域监管入口）。"""
    bureaus = {
        "长江流域生态环境监督管理局": "https://cjjg.mee.gov.cn",
        "黄河流域生态环境监督管理局": "https://huanghejg.mee.gov.cn",
        "淮河流域生态环境监督管理局": "https://huaihejg.mee.gov.cn",
        "海河流域北海海域生态环境监督管理局": "https://hhbhjg.mee.gov.cn",
        "珠江流域南海海域生态环境监督管理局": "https://zjnhjg.mee.gov.cn",
        "太湖流域东海海域生态环境监督管理局": "https://thdhjg.mee.gov.cn",
    }
    return {"count": len(bureaus), "bureaus": bureaus, "source": "https://www.mee.gov.cn/zjhb"}
