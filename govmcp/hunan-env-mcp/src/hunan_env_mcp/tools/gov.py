"""政务栏目类 MCP 工具（数据源：sthjt.hunan.gov.cn 静态栏目页）。"""
from __future__ import annotations

import re

from .. import config
from ..datasource import web_crawler


def _channel_list(channel_key: str, page: int = 1, keyword: str | None = None) -> list[dict]:
    items = web_crawler.list_articles(channel_key, page=page)
    if keyword:
        kw = keyword.strip()
        items = [i for i in items if kw in i["title"] or kw in i.get("date", "")]
    return items


def _detail_public(detail_url: str) -> dict:
    return web_crawler.get_detail(detail_url)


def eia_publicity_search(
    type: str = "accept", keyword: str | None = None, page: int = 1
) -> list[dict]:
    """检索湖南省建设项目环境影响评价（环评）公示信息。

    Args:
        type: 公示阶段，可选 accept(受理) / review(拟审批) / decision(审批决定)，默认 accept。
        keyword: 可选，按标题关键词过滤（项目名称/建设单位等）。
        page: 页码，从 1 开始，每页约 20 条。

    Returns:
        公示列表（标题/日期/详情页 URL）。
    """
    mapping = {"accept": "eia_accept", "review": "eia_review", "decision": "eia_decision"}
    key = mapping.get(type, "eia_accept")
    return _channel_list(key, page=page, keyword=keyword)


def policy_document_search(
    category: str = "policy", keyword: str | None = None, page: int = 1
) -> list[dict]:
    """检索湖南省生态环境厅政策文件（规范性文件/政策解读）。

    Args:
        category: 可选 policy(规范性文件) / interpret(政策解读)，默认 policy。
        keyword: 可选，标题关键词。
        page: 页码，从 1 开始。

    Returns:
        政策文件列表（标题/日期/详情页 URL）。
    """
    key = "policy" if category == "policy" else "policy_interpret"
    return _channel_list(key, page=page, keyword=keyword)


def notice_announcement_list(keyword: str | None = None, page: int = 1) -> list[dict]:
    """查询湖南省生态环境厅通知公告。

    Args:
        keyword: 可选，标题关键词。
        page: 页码，从 1 开始（该栏目约 1593 条、80 页）。

    Returns:
        通知公告列表（标题/日期/详情页 URL）。
    """
    return _channel_list("notice", page=page, keyword=keyword)


def environmental_quality_monthly(year: int | None = None, month: int | None = None) -> list[dict]:
    """查询湖南省环境质量月报/年报信息。

    Args:
        year: 可选，年份（如 2026）。
        month: 可选，月份（1-12）；不传月份时返回全年列表。

    Returns:
        环境质量状况文章列表（标题/日期/详情页 URL）。
    """
    items = _channel_list("env_quality_monthly", page=1)
    if year:
        items = [i for i in items if str(year) in i.get("date", "")]
    if month:
        items = [i for i in items if f"-{month:02d}-" in i.get("date", "")]
    return items


def env_statistics_report(year: int | None = None) -> list[dict]:
    """查询湖南省生态环境统计年报。

    Args:
        year: 可选，年份（如 2024）。

    Returns:
        统计年报文章列表。
    """
    items = _channel_list("env_statistics", page=1)
    if year:
        items = [i for i in items if str(year) in i.get("date", "")]
    return items


def enforcement_case_search(keyword: str | None = None, page: int = 1) -> list[dict]:
    """检索湖南省生态环境行政执法案例/处罚决定书公开信息。

    Args:
        keyword: 可选，标题关键词。
        page: 页码，从 1 开始。

    Returns:
        执法公开文章列表。
    """
    return _channel_list("enforcement", page=page, keyword=keyword)


def credit_evaluation_query(year: int | None = None, keyword: str | None = None) -> list[dict]:
    """查询湖南省企事业单位环保信用评价结果。

    Args:
        year: 可选，年度（如 2024）。
        keyword: 可选，标题关键词。

    Returns:
        信用评价公告列表。
    """
    items = _channel_list("credit_evaluation", page=1, keyword=keyword)
    if year:
        items = [i for i in items if str(year) in i.get("date", "")]
    return items


def document_detail(detail_url: str) -> dict:
    """解析任意湖南省生态环境厅官网详情页的完整内容。

    Args:
        detail_url: 详情页完整 URL（形如 https://sthjt.hunan.gov.cn/sthjt/xxgk/.../t20260826_34051299.html）。

    Returns:
        标题/发布机构/日期/正文/附件列表。
    """
    if not re.search(config.DETAIL_RE_PATTERN, detail_url):
        raise ValueError("请提供有效的官网详情页 URL（含 tYYYYMMDD_id.html 特征）")
    return _detail_public(detail_url)


# ---- P0 扩展工具（2026-08-27 全站穿透实测） ----

_NEWS_CHANNELS = {
    "zxdt": "news_zxdt",      # 环保动态
    "hjyw": "news_hjyw",      # 环境要闻
    "szxw": "news_szxw",      # 市州新闻
    "c101666": "news_c101666",  # 时政关注
    "tpxw": "news_tpxw",      # 图片新闻
}

_INTERACTION_CHANNELS = {
    "survey_topic": "survey_topic",      # 调查征集主题
    "survey_feedback": "survey_feedback",  # 调查征集反馈
    "interview": "online_interview",     # 在线访谈
}

_DOMAIN_CHANNELS = {
    "nuclear": "nuclear_radiation",      # 核与辐射
    "eia": "eia_field",                  # 环境影响评价
    "emergency": "emergency",            # 应急管理
    "eco": "eco_protection",             # 生态保护（示范创建）
    "soil": "soil_pollution",            # 土壤污染防治
}


def news_dynamic_list(channel: str = "zxdt", keyword: str | None = None, page: int = 1) -> list[dict]:
    """查询湖南省生态环境厅新闻动态（环保动态/环境要闻/市州新闻/时政关注/图片新闻）。

    Args:
        channel: 频道，可选 zxdt(环保动态) / hjyw(环境要闻) / szxw(市州新闻) / c101666(时政关注) / tpxw(图片新闻)，默认 zxdt。
        keyword: 可选，标题关键词。
        page: 页码，从 1 开始，每页约 20 条。

    Returns:
        新闻列表（标题/日期/详情页 URL）。
    """
    key = _NEWS_CHANNELS.get(channel, "news_zxdt")
    return _channel_list(key, page=page, keyword=keyword)


def interaction_list(kind: str = "survey_topic", keyword: str | None = None, page: int = 1) -> list[dict]:
    """查询湖南省生态环境厅互动交流栏目（调查征集主题/结果反馈/在线访谈）。

    Args:
        kind: 类型，可选 survey_topic(征集主题) / survey_feedback(结果反馈) / interview(在线访谈)，默认 survey_topic。
        keyword: 可选，标题关键词。
        page: 页码，从 1 开始。

    Returns:
        互动交流列表（标题/日期/详情页 URL）。
    """
    key = _INTERACTION_CHANNELS.get(kind, "survey_topic")
    return _channel_list(key, page=page, keyword=keyword)


def key_domain_list(domain: str = "nuclear", keyword: str | None = None, page: int = 1) -> list[dict]:
    """查询湖南省生态环境厅重点领域公开信息（核与辐射/环评/应急管理/生态保护/土壤污染防治）。

    Args:
        domain: 领域，可选 nuclear(核与辐射) / eia(环境影响评价) / emergency(应急管理) / eco(生态保护-示范创建) / soil(土壤污染防治)，默认 nuclear。
        keyword: 可选，标题关键词。
        page: 页码，从 1 开始。

    Returns:
        重点领域文章列表（标题/日期/详情页 URL）。
    """
    key = _DOMAIN_CHANNELS.get(domain, "nuclear_radiation")
    return _channel_list(key, page=page, keyword=keyword)


# ---- P1 扩展工具（2026-08-27 全站穿透实测） ----

_LEGAL_CHANNELS = {
    "local_regulation": "local_regulation",  # 地方性法规
    "case_example": "case_example",          # 以案说法
}

_MGMT_CHANNELS = {
    "enforce_supervision": "enforce_supervision",  # 行政执法事前事中
    "special_fund": "special_fund",                # 专项资金管理
    "plan": "plan_program",                        # 规划计划
    "cppcc": "proposal_cppcc",                     # 政协提案答复
    "annual_report": "annual_report",              # 信息公开年报
    "complaint": "complaint_report",               # 投诉举报情况
}


def legal_document_list(category: str = "local_regulation", keyword: str | None = None, page: int = 1) -> list[dict]:
    """查询湖南省生态环境厅法规类公开文件（地方性法规/以案说法）。

    Args:
        category: 类型，可选 local_regulation(地方性法规) / case_example(以案说法)，默认 local_regulation。
        keyword: 可选，标题关键词。
        page: 页码，从 1 开始。

    Returns:
        法规文件列表（标题/日期/详情页 URL）。
    """
    key = _LEGAL_CHANNELS.get(category, "local_regulation")
    return _channel_list(key, page=page, keyword=keyword)


def management_public_list(category: str = "plan", keyword: str | None = None, page: int = 1) -> list[dict]:
    """查询湖南省生态环境厅管理与监督公开信息（执法事前事中/专项资金/规划计划/政协提案/公开年报/投诉举报）。

    Args:
        category: 类别，可选 enforce_supervision(执法事前事中) / special_fund(专项资金) / plan(规划计划) / cppcc(政协提案答复) / annual_report(信息公开年报) / complaint(投诉举报情况)，默认 plan。
        keyword: 可选，标题关键词。
        page: 页码，从 1 开始。

    Returns:
        管理公开信息列表（标题/日期/详情页 URL）。
    """
    key = _MGMT_CHANNELS.get(category, "plan_program")
    return _channel_list(key, page=page, keyword=keyword)


# ---- P2/P3 扩展工具（2026-08-27 全站穿透实测） ----

_ORG_CHANNELS = {
    "leader": "org_leader",    # 机构领导
    "depart": "org_depart",    # 内设机构
    "unit": "org_unit",        # 直属机构
    "hr": "hr_info",           # 人事信息
}

_MEDIA_CHANNELS = {
    "video": "media_video",    # 环保视频
    "press": "media_press",    # 新闻发布会
    "qa": "media_qa",          # 新媒体问政
}


def org_structure_list(scope: str = "leader", keyword: str | None = None) -> list[dict]:
    """查询湖南省生态环境厅机构静态信息（机构领导/内设机构/直属机构/人事信息）。

    Args:
        scope: 范围，可选 leader(机构领导) / depart(内设机构) / unit(直属机构) / hr(人事信息)，默认 leader。
        keyword: 可选，标题关键词。

    Returns:
        机构信息列表（标题/日期/详情页 URL）。
    """
    key = _ORG_CHANNELS.get(scope, "org_leader")
    return _channel_list(key, page=1, keyword=keyword)


def media_center_list(kind: str = "video", keyword: str | None = None, page: int = 1) -> list[dict]:
    """查询湖南省生态环境厅媒体互动栏目（环保视频/新闻发布会/新媒体问政）。

    Args:
        kind: 类型，可选 video(环保视频) / press(新闻发布会) / qa(新媒体问政)，默认 video。
        keyword: 可选，标题关键词。
        page: 页码，从 1 开始。

    Returns:
        媒体互动内容列表（标题/日期/详情页 URL）。
    """
    key = _MEDIA_CHANNELS.get(kind, "media_video")
    return _channel_list(key, page=page, keyword=keyword)
