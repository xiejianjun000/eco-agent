"""辐射与核安全领域：空气吸收剂量率、核安全监管入口。"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

RADIATION_PLATFORM = "http://data.rmtc.org.cn:8080/gis/PubIndex.html"
NNSA = "https://nnsa.mee.gov.cn"


# 国家核安全局子站栏目 -> news.CATEGORY_URLS 栏目名
NNSA_SECTIONS: dict[str, str] = {
    "工作动态": "核安全局工作动态",
    "政策文件": "核安全局政策文件",
    "机构职能": "核安全局机构",
}


def list_nnsa_sections() -> dict:
    """列出国家核安全局子站可读栏目。"""
    return {
        "count": len(NNSA_SECTIONS),
        "sections": [{"section": s, "category": c} for s, c in NNSA_SECTIONS.items()],
        "note": "使用 read_nnsa_list(section=...) 读取核安全局子站最新列表",
    }


def read_nnsa_list(fetcher, cache, section: str = "工作动态", limit: int = 15) -> dict:
    """读取国家核安全局子站栏目最新列表。"""
    category = NNSA_SECTIONS.get(section)
    if not category:
        return {"section": section, "items": [], "note": f"未知栏目：{section}；可用 list_nnsa_sections() 查看"}
    from .news import read_mee_list

    data = read_mee_list(fetcher, cache, category, limit=limit)
    data["section"] = section
    return data


def read_radiation_level(fetcher, cache, region: Optional[str] = None) -> dict:
    """读取全国空气吸收剂量率发布数据。来源：辐射环境监测技术中心。"""
    key = f"radiation:{region or 'all'}"
    cached = cache.get(key)
    if cached:
        return {**cached, "cache": "hit"}
    result = {"region": region or "全国", "source": RADIATION_PLATFORM, "content": "", "note": ""}
    try:
        html = fetcher.get_text(RADIATION_PLATFORM)
        from ..core.parser import parse_article, parse_table
        table = parse_table(html, limit=20)
        if table:
            result["table"] = table
        text = parse_article(html, max_chars=3000)
        if text:
            result["content"] = text
        else:
            result["note"] = "辐射发布系统为 GIS 动态页面，未解析到数据；建议升级 Playwright 浏览器抓取"
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)
    cache.set(key, result, ttl=600)
    return result


def list_nuclear_entrances() -> dict:
    """列出核与辐射安全核心系统入口（百科知识域：核安全）。"""
    return {
        "国家核安全局": NNSA,
        "核技术利用辐射安全申报系统": "http://rr.mee.gov.cn/rsmsreq/login.jsp",
        "核技术利用辐射安全监管系统": "https://rm.mee.gov.cn/",
        "核技术利用辐射安全培训平台": "http://fushe.mee.gov.cn/",
        "核与辐射安全中心": "https://www.chinansc.cn",
        "source": NNSA,
    }
