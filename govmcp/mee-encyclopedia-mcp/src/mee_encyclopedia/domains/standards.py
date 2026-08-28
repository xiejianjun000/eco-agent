"""标准领域：生态环境标准目录检索、标准详情。"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

STD_INDEX = "https://www.mee.gov.cn/ywgz/fgbz/bz/"


def search_standard(fetcher, cache, keyword: str, limit: int = 10) -> dict:
    """按关键词检索生态环境标准（HJ/GB 目录）。来源：生态环境部标准专栏。"""
    key = f"std:search:{keyword}:{limit}"
    cached = cache.get(key)
    if cached:
        return {**cached, "cache": "hit"}
    result = {"keyword": keyword, "source": STD_INDEX, "items": [], "note": ""}
    try:
        html = fetcher.get_text(STD_INDEX)
        from ..core.parser import parse_links
        links = parse_links(html, base_url=STD_INDEX, limit=200)
        items = [lk for lk in links if keyword in lk["title"]][:limit]
        result["items"] = items
        if not items:
            result["note"] = "目录页未命中关键词，标准目录可能分页或为动态加载；建议尝试 HJ 编号精确检索"
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)
    cache.set(key, result, ttl=3600, slow=True)
    return result


def read_standard(fetcher, cache, standard_no: str) -> dict:
    """按编号读取标准信息（如 HJ 1294—2023）。"""
    key = f"std:detail:{standard_no}"
    cached = cache.get(key)
    if cached:
        return {**cached, "cache": "hit"}
    result = {"standard_no": standard_no, "source": STD_INDEX, "info": {}, "note": ""}
    no = standard_no.upper().replace(" ", "")
    try:
        html = fetcher.get_text(STD_INDEX)
        from ..core.parser import parse_links
        links = parse_links(html, base_url=STD_INDEX, limit=300)
        m = re.search(r"(\d{3,4})", no)
        num = m.group(1) if m else ""
        hit = next((lk for lk in links if num and num in lk["title"] and "标准" in lk["title"]), None)
        if hit:
            result["info"] = {"title": hit["title"], "url": hit["url"]}
        else:
            result["note"] = "未在目录页定位到该编号；可尝试 download_standard_pdf 直接检索标准文本"
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)
    cache.set(key, result, ttl=3600, slow=True)
    return result


def list_standard_categories() -> dict:
    """列出生态环境标准体系分类（百科知识域：标准体系导览）。"""
    return {
        "source": STD_INDEX,
        "categories": [
            "生态环境质量标准",
            "生态环境风险管控标准",
            "污染物排放标准",
            "生态环境监测标准",
            "生态环境管理规范",
            "生态环境基础标准",
        ],
        "note": "依据《生态环境标准管理办法》分类",
    }
