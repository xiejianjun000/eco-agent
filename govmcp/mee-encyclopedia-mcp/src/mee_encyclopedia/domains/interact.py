"""互动交流与综合栏目：意见征集、留言选登、常见问题、党建、专题、曝光台、英文版。

- 意见征集/留言选登/常见问题/党建/专题/曝光台：复用 news.read_mee_list 栏目读取
- 英文版（english.mee.gov.cn）：独立列表读取
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

BASE = "https://www.mee.gov.cn"
EN = "http://english.mee.gov.cn"

# 互动交流栏目 -> news.CATEGORY_URLS 栏目名
INTERACT_SECTIONS: dict[str, str] = {
    "意见征集-专题意见": "意见征集-专题意见",
    "意见征集-网上征集": "意见征集-网上征集",
    "留言选登": "留言选登",
    "常见问题": "常见问题",
}

# 曝光台栏目 -> news.CATEGORY_URLS 栏目名
EXPOSURE_SECTIONS: dict[str, str] = {
    "行政处理": "行政处理",
    "执法信息": "执法信息",
    "通报": "通报",
}

# 英文版栏目 URL
ENGLISH_SECTIONS: dict[str, str] = {
    "首页": f"{EN}/",
    "关于我们": f"{EN}/About_MEE/",
    "新闻动态": f"{EN}/News_service/",
    "新闻发布": f"{EN}/News_service/news_release/",
    "媒体新闻": f"{EN}/News_service/media_news/",
    "图片新闻": f"{EN}/News_service/Photo/",
    "国际合作": f"{EN}/Events/international_cooperation/",
    "重大活动": f"{EN}/Events/major_events/",
    "专题": f"{EN}/Events/Special_Topics/",
    "政策资源": f"{EN}/Resources/Policies/",
}


def list_interact_sections() -> dict:
    """列出互动交流与综合栏目导览。"""
    return {
        "interact": list(INTERACT_SECTIONS.keys()),
        "exposure": list(EXPOSURE_SECTIONS.keys()),
        "english": list(ENGLISH_SECTIONS.keys()),
        "other": ["机关党建", "历史专题"],
        "note": "使用 read_interact / read_exposure / read_english_list 读取对应栏目",
    }


def read_interact(fetcher, cache, section: str = "常见问题", limit: int = 15) -> dict:
    """读取互动交流栏目（意见征集/留言选登/常见问题）最新列表。"""
    category = INTERACT_SECTIONS.get(section)
    if not category:
        return {"section": section, "items": [], "note": f"未知互动栏目：{section}；可用 list_interact_sections() 查看"}
    from .news import read_mee_list

    data = read_mee_list(fetcher, cache, category, limit=limit)
    data["section"] = section
    return data


def read_exposure(fetcher, cache, section: str = "通报", limit: int = 15) -> dict:
    """读取曝光台栏目（行政处理/执法信息/通报）最新列表。"""
    category = EXPOSURE_SECTIONS.get(section)
    if not category:
        return {"section": section, "items": [], "note": f"未知曝光台栏目：{section}；可用 list_interact_sections() 查看"}
    from .news import read_mee_list

    data = read_mee_list(fetcher, cache, category, limit=limit)
    data["section"] = section
    return data


def read_english_list(fetcher, cache, section: str = "新闻发布", limit: int = 15) -> dict:
    """读取生态环境部英文版栏目最新列表。"""
    url = ENGLISH_SECTIONS.get(section)
    if not url:
        return {"section": section, "items": [], "note": f"未知英文栏目：{section}；可用 list_interact_sections() 查看"}
    key = f"english:{section}:{limit}"
    cached = cache.get(key)
    if cached:
        return {**cached, "cache": "hit"}
    result = {"section": section, "source": url, "items": [], "note": ""}
    try:
        html = fetcher.get_text(url)
        from ..core.parser import parse_links

        links = parse_links(html, base_url=url, limit=120)
        items = [
            lk for lk in links
            if lk["title"] and len(lk["title"]) >= 5
            and lk["title"].strip() != lk["url"].rstrip("/")
            and "english.mee.gov.cn" in lk["url"]
        ][:limit]
        result["items"] = items
        if not items:
            result["note"] = "未解析到条目，英文版栏目结构可能变化"
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)
    cache.set(key, result, ttl=1800, slow=True)
    return result
