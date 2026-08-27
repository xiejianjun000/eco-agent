"""主站动态领域：要闻、公示、业务栏目、政策分类、质量报告等统一列表读取。

设计说明：
- 全部栏目（60+）集中在 CATEGORY_URLS，按 CATEGORY_GROUPS 分组；
- read_mee_list 是唯一列表读取实现，支持全部栏目与关键词过滤；
- 栏目 URL 来自 2026-08-27 官网穿透式实测（全部验证 200 且有正文）。
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

BASE = "https://www.mee.gov.cn"
NNSA = "https://nnsa.mee.gov.cn"

# ---------------- 栏目分组（导览用） ----------------
CATEGORY_GROUPS: dict[str, list[str]] = {
    "要闻动态": ["要闻动态", "时政要闻", "环境要闻", "地方快讯", "新闻发布", "直播访谈", "公示公告", "视频新闻"],
    "政策文件": [
        "政策文件", "中央有关文件", "国务院有关文件", "部令", "部公告", "部文件", "部函",
        "办公厅文件", "办公厅函", "行政审批文件", "核安全局文件", "核安全局函", "其他", "政策解读",
    ],
    "业务工作": [
        "督察", "法规标准", "政策规划与业务综合", "行政体制与人事", "科技与财务",
        "自然生态保护", "水生态环境", "海洋生态环境", "大气环境保护", "应对气候变化",
        "土壤生态环境", "固废化学品", "核与辐射安全监管", "环境影响评价", "排污许可",
        "生态环境监测", "生态环境执法", "国际交流合作", "宣传教育", "环境应急", "投诉举报",
    ],
    "环境质量": [
        "环境质量", "生态环境状况公报", "生态环境统计年报", "海洋公报", "噪声防治报告",
        "固废年报", "移动源年报", "地表水水质月报", "全国地表水质量状况", "海水浴场水质",
        "全国空气质量状况", "空气质量预报", "城市空气质量报告",
    ],
    "互动交流": ["意见征集-专题意见", "意见征集-网上征集", "留言选登", "常见问题"],
    "曝光台": ["行政处理", "执法信息", "通报"],
    "核安全局": ["核安全局工作动态", "核安全局政策文件", "核安全局机构"],
    "其他": ["机关党建", "历史专题"],
}

# ---------------- 栏目 URL 映射（全部实测有效） ----------------
CATEGORY_URLS: dict[str, str] = {
    # 要闻动态
    "要闻动态": f"{BASE}/ywdt/",
    "时政要闻": f"{BASE}/ywdt/szyw/",
    "环境要闻": f"{BASE}/ywdt/hjywnews/",
    "地方快讯": f"{BASE}/ywdt/dfnews/",
    "新闻发布": f"{BASE}/ywdt/xwfb/",
    "直播访谈": f"{BASE}/ywdt/zbft/",
    "公示公告": f"{BASE}/ywdt/gsgg/",
    "视频新闻": f"{BASE}/ywdt/spxw/",
    # 政策文件
    "政策文件": f"{BASE}/zcwj/",
    "中央有关文件": f"{BASE}/zcwj/zyygwj/",
    "国务院有关文件": f"{BASE}/zcwj/gwywj/",
    "部令": f"{BASE}/zcwj/bwj/ling/",
    "部公告": f"{BASE}/zcwj/bwj/gg/",
    "部文件": f"{BASE}/zcwj/bwj/wj/",
    "部函": f"{BASE}/zcwj/bwj/han/",
    "办公厅文件": f"{BASE}/zcwj/bgtwj/wj/",
    "办公厅函": f"{BASE}/zcwj/bgtwj/han/",
    "行政审批文件": f"{BASE}/zcwj/xzspwj/",
    "核安全局文件": f"{BASE}/zcwj/haqjwj/wj/",
    "核安全局函": f"{BASE}/zcwj/haqjwj/han/",
    "其他": f"{BASE}/zcwj/qt/",
    "政策解读": f"{BASE}/zcwj/zcjd/",
    # 业务工作 21 栏目
    "督察": f"{BASE}/ywgz/zysthjbhdc/",
    "法规标准": f"{BASE}/ywgz/fgbz/",
    "政策规划与业务综合": f"{BASE}/ywgz/zcghtjdd/",
    "行政体制与人事": f"{BASE}/ywgz/xztzyrs/",
    "科技与财务": f"{BASE}/ywgz/kjycw/",
    "自然生态保护": f"{BASE}/ywgz/zrstbh/",
    "水生态环境": f"{BASE}/ywgz/ssthjbh/",
    "海洋生态环境": f"{BASE}/ywgz/hysthjbh/",
    "大气环境保护": f"{BASE}/ywgz/dqhjbh/",
    "应对气候变化": f"{BASE}/ywgz/ydqhbh/",
    "土壤生态环境": f"{BASE}/ywgz/trsthjbh/",
    "固废化学品": f"{BASE}/ywgz/gtfwyhxpgl/",
    "核与辐射安全监管": f"{BASE}/ywgz/hyfsaqjg/",
    "环境影响评价": f"{BASE}/ywgz/hjyxpj/",
    "排污许可": f"{BASE}/ywgz/pwxkgl/",
    "生态环境监测": f"{BASE}/ywgz/sthjjcgl/",
    "生态环境执法": f"{BASE}/ywgz/sthjzf/",
    "国际交流合作": f"{BASE}/ywgz/gjjlhz/",
    "宣传教育": f"{BASE}/ywgz/xcjy/",
    "环境应急": f"{BASE}/ywgz/hjyj/",
    "投诉举报": f"{BASE}/ywgz/hjwrjb/",
    # 环境质量报告
    "环境质量": f"{BASE}/hjzl/",
    "生态环境状况公报": f"{BASE}/hjzl/sthjzk/zghjzkgb/",
    "生态环境统计年报": f"{BASE}/hjzl/sthjzk/sthjtjnb/",
    "海洋公报": f"{BASE}/hjzl/sthjzk/jagb/",
    "噪声防治报告": f"{BASE}/hjzl/sthjzk/hjzywr/",
    "固废年报": f"{BASE}/hjzl/sthjzk/gtfwwrfz/",
    "移动源年报": f"{BASE}/hjzl/sthjzk/ydyhjgl/",
    "地表水水质月报": f"{BASE}/hjzl/shj/dbsszyb/",
    "全国地表水质量状况": f"{BASE}/hjzl/shj/qgdbszlzk/",
    "海水浴场水质": f"{BASE}/hjzl/shj/hsycszzb/",
    "全国空气质量状况": f"{BASE}/hjzl/dqhj/qgkqzlzk/",
    "空气质量预报": f"{BASE}/hjzl/dqhj/kqzlyb/",
    "城市空气质量报告": f"{BASE}/hjzl/dqhj/cskqzlzkyb/",
    # 互动交流
    "意见征集-专题意见": f"{BASE}/hdjl/yjzj/zjyj/",
    "意见征集-网上征集": f"{BASE}/hdjl/yjzj/wqzj_1/",
    "留言选登": f"{BASE}/hdjl/lyxd/",
    "常见问题": f"{BASE}/hdjl/cjwt/",
    # 曝光台
    "行政处理": f"{BASE}/ywdt/bgt/xzcf/",
    "执法信息": f"{BASE}/ywdt/bgt/zfxx/",
    "通报": f"{BASE}/ywdt/bgt/tb/",
    # 其他
    "机关党建": f"{BASE}/djgz/jgdj/",
    "历史专题": f"{BASE}/ztzl/lszt/",
    # 国家核安全局子站
    "核安全局工作动态": f"{NNSA}/ywdt/gzdt/",
    "核安全局政策文件": f"{NNSA}/zcwj/",
    "核安全局机构": f"{NNSA}/zjjg/zyzz/",
}

# 解析列表时需要过滤的导航/外链噪音
_NOISE_TITLES = {
    "更多", "更多>", "更多 >", "邮箱", "EN", "返回", "返回生态环境部首页",
    "点击进入", "外交部", "文件", "解读", "留言选登", "常见问题",
}
_NOISE_URL_MARK = [
    "mail.mee.gov.cn", "english.mee.gov.cn", "zwfw.mee.gov.cn",
    "sousuo.mee.gov.cn", "/home/wbwx/", "/home/wzdt/", "fmprc.gov.cn",
]


def list_mee_categories() -> dict:
    """返回全部可读栏目分组导览。"""
    return {
        "count": len(CATEGORY_URLS),
        "groups": {g: {"categories": CATS, "count": len(CATS)} for g, CATS in CATEGORY_GROUPS.items()},
        "note": "使用 read_mee_list(category=...) 读取对应栏目最新列表",
    }


def read_mee_list(fetcher, cache, category: str = "要闻动态", limit: int = 20, keyword: Optional[str] = None) -> dict:
    """读取生态环境部主站（含核安全局子站）指定栏目最新列表。"""
    url = CATEGORY_URLS.get(category)
    if not url:
        return {
            "category": category,
            "items": [],
            "note": f"未知栏目：{category}；可用 list_mee_categories() 查看全部栏目",
        }
    key = f"news:{category}:{limit}:{keyword or ''}"
    cached = cache.get(key)
    if cached:
        return {**cached, "cache": "hit"}
    result = {"category": category, "source": url, "items": [], "note": ""}
    try:
        html = fetcher.get_text(url)
        from ..core.parser import parse_links
        links = parse_links(html, base_url=url, limit=120)
        items = [
            lk for lk in links
            if lk["title"] and len(lk["title"]) >= 6
            and lk["title"].strip() not in _NOISE_TITLES
            and lk["title"].strip() != lk["url"].rstrip("/")
            and not any(m in lk["url"] for m in _NOISE_URL_MARK)
        ]
        if keyword:
            items = [it for it in items if keyword in it["title"]]
        result["items"] = items[:limit]
        if not items:
            result["note"] = "未解析到文章条目，栏目结构可能变化或为动态加载"
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)
    cache.set(key, result, ttl=1800, slow=True)
    return result


def read_mee_article(fetcher, cache, url: str) -> dict:
    """读取主站单篇文章正文（要闻/政策/公示详情）。"""
    key = f"article:{url}"
    cached = cache.get(key)
    if cached:
        return {**cached, "cache": "hit"}
    result = {"url": url, "title": "", "content": "", "note": ""}
    try:
        html = fetcher.get_text(url)
        import re

        # 站外跳转提示页：提取"继续访问"目标并跟随一次
        if "即将离开" in html or "继续访问" in html:
            m = re.search(r'href=["\'](https?://[^"\']+)["\'][^>]*>\s*继续访问', html, re.S | re.I) or \
                re.search(r'继续访问[^<]*<a[^>]+href=["\'](https?://[^"\']+)["\']', html, re.S | re.I)
            if not m:
                m = re.search(r'href=["\'](https?://(?!.*mee\.gov\.cn)[^"\']+)["\']', html, re.S | re.I)
            if m:
                html = fetcher.get_text(m.group(1))
                url = m.group(1)
        from ..core.parser import parse_article

        m = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
        result["title"] = m.group(1).strip() if m else ""
        result["content"] = parse_article(html, max_chars=10000)
        result["final_url"] = url
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)
    cache.set(key, result, ttl=3600, slow=True)
    return result
