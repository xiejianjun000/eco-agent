"""政策法规领域：政策文件检索、全文读取。"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

POLICY_INDEX = "https://www.mee.gov.cn/zcwj/"
LAW_INDEX = "https://www.mee.gov.cn/ywgz/fgbz/fl/"


# 政策文种 -> news.CATEGORY_URLS 栏目名
POLICY_TYPES: dict[str, str] = {
    "中央有关文件": "中央有关文件",
    "国务院有关文件": "国务院有关文件",
    "部令": "部令",
    "部公告": "部公告",
    "部文件": "部文件",
    "部函": "部函",
    "办公厅文件": "办公厅文件",
    "办公厅函": "办公厅函",
    "行政审批文件": "行政审批文件",
    "核安全局文件": "核安全局文件",
    "核安全局函": "核安全局函",
    "其他文件": "其他",
    "政策解读": "政策解读",
}


def list_policy_types() -> dict:
    """列出全部政策文种分类（供 read_policy_type 使用）。"""
    return {
        "count": len(POLICY_TYPES),
        "types": [{"type": t, "category": c} for t, c in POLICY_TYPES.items()],
        "note": "使用 read_policy_type(doc_type=...) 读取对应文种最新政策",
    }


def read_policy_type(fetcher, cache, doc_type: str = "部令", limit: int = 15) -> dict:
    """按文种读取政策文件最新列表（部令/公告/文件/函/中央/国务院/行政审批/核安全局/解读）。"""
    category = POLICY_TYPES.get(doc_type)
    if not category:
        return {"doc_type": doc_type, "items": [], "note": f"未知文种：{doc_type}；可用 list_policy_types() 查看"}
    from .news import read_mee_list

    data = read_mee_list(fetcher, cache, category, limit=limit)
    data["doc_type"] = doc_type
    return data


def search_policy(fetcher, cache, keyword: str, limit: int = 10) -> dict:
    """按关键词检索政策文件（部令/规范性文件/解读）。来源：主站政策文件栏目。"""
    key = f"policy:search:{keyword}:{limit}"
    cached = cache.get(key)
    if cached:
        return {**cached, "cache": "hit"}
    result = {"keyword": keyword, "source": POLICY_INDEX, "items": [], "note": ""}
    try:
        html = fetcher.get_text(POLICY_INDEX)
        from ..core.parser import parse_links
        links = parse_links(html, base_url=POLICY_INDEX, limit=200)
        items = [lk for lk in links if keyword in lk["title"] and len(lk["title"]) >= 8][:limit]
        result["items"] = items
        if not items:
            result["note"] = "未命中关键词；政策目录按年份分页，可尝试更精确关键词"
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)
    cache.set(key, result, ttl=3600, slow=True)
    return result


def read_policy(fetcher, cache, url: str) -> dict:
    """读取政策文件全文正文。"""
    key = f"policy:read:{url}"
    cached = cache.get(key)
    if cached:
        return {**cached, "cache": "hit"}
    result = {"url": url, "title": "", "content": "", "note": ""}
    try:
        html = fetcher.get_text(url)
        from ..core.parser import parse_article
        import re

        m = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
        result["title"] = m.group(1).strip() if m else ""
        result["content"] = parse_article(html, max_chars=12000)
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)
    cache.set(key, result, ttl=3600, slow=True)
    return result


def list_laws() -> dict:
    """列出生态环境法律法规体系（百科知识域：法规导览）。"""
    return {
        "source": LAW_INDEX,
        "note": "生态环境法律法规体系概览（示例核心法规）",
        "laws": [
            "中华人民共和国环境保护法",
            "中华人民共和国环境影响评价法",
            "中华人民共和国大气污染防治法",
            "中华人民共和国水污染防治法",
            "中华人民共和国土壤污染防治法",
            "中华人民共和国固体废物污染环境防治法",
            "中华人民共和国噪声污染防治法",
            "中华人民共和国放射性污染防治法",
            "中华人民共和国海洋环境保护法",
            "中华人民共和国长江保护法",
            "中华人民共和国黄河保护法",
        ],
    }
