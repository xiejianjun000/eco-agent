"""站内搜索：生态环境部官网 searchnew 接口封装。

接口：https://www.mee.gov.cn/searchnew/?searchword=关键词
仅使用公开只读搜索，不登录、不提交表单之外的数据。
"""
from __future__ import annotations

import logging
import urllib.parse

logger = logging.getLogger(__name__)

SEARCH_URL = "https://www.mee.gov.cn/searchnew/"


def search_site(fetcher, cache, keyword: str, limit: int = 15) -> dict:
    """站内关键词搜索，返回官网内相关文章/栏目链接列表。"""
    if not keyword or not keyword.strip():
        return {"keyword": keyword, "items": [], "note": "keyword 不能为空"}
    kw = keyword.strip()
    key = f"search:{kw}:{limit}"
    cached = cache.get(key)
    if cached:
        return {**cached, "cache": "hit"}
    url = f"{SEARCH_URL}?{urllib.parse.urlencode({'searchword': kw})}"
    result = {"keyword": kw, "source": url, "items": [], "note": ""}
    try:
        html = fetcher.get_text(url)
        from ..core.parser import parse_links

        links = parse_links(html, base_url=url, limit=200)
        items = [
            lk for lk in links
            if lk["title"] and len(lk["title"]) >= 6
            and lk["title"].strip() != lk["url"].rstrip("/")
            and any(m in lk["url"] for m in ("mee.gov.cn", "nnsa.mee.gov.cn"))
            and not any(m in lk["url"] for m in ("mail.mee.gov.cn", "english.mee.gov.cn", "zwfw.mee.gov.cn"))
        ][:limit]
        result["items"] = items
        if not items:
            result["note"] = "未解析到搜索结果（搜索页可能动态加载），可改用 read_mee_list 栏目读取"
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)
    cache.set(key, result, ttl=1800, slow=True)
    return result
