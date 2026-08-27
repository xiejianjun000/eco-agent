"""站点常量与全局配置。

所有可调参数均支持环境变量覆盖，便于部署与限流控制。
"""
from __future__ import annotations

import os


def _load_dotenv_simple(path: str) -> None:
    """极简 .env 加载（避免额外依赖）；已存在的环境变量优先，不覆盖。"""
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip().strip('"').strip("'")
            if key:
                os.environ.setdefault(key, val)


# 工程根目录 .env（src/hunan_env_mcp/config.py 上溯两级）
_ENV_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", ".env"
)
_load_dotenv_simple(_ENV_FILE)

# ---- 站点基础 ----
BASE_URL = "https://sthjt.hunan.gov.cn"
SITE_ID = "115000000"  # 湖南政府统一搜索平台中的站点 ID
SEARCH_URL = "http://searching.hunan.gov.cn/hunan"

# ---- 实时空气质量 API（第三方服务商，探明于官网首页 iframe） ----
AIR_API_BASE = os.getenv(
    "HUNAN_AIR_API_BASE", "https://hn.leitesoft.cn:9020/HNAirWebAPI/api"
)
AIR_API_USER = os.getenv("HUNAN_AIR_API_USER", "hnapp")
# 密码需从官网首页 iframe（https://hn.leitesoft.cn:8031/HN/*.html）页面 JS 中提取，
# 本仓库不内置凭据，未配置时相关工具会返回明确提示。
AIR_API_PASSWORD = os.getenv("HUNAN_AIR_API_PASSWORD", "")

# ---- 限速与缓存 ----
RATE_LIMIT_RPS = float(os.getenv("HUNAN_RATE_LIMIT_RPS", "1.0"))  # 全局限速：1 req/s
CACHE_HTML_TTL = int(os.getenv("HUNAN_CACHE_HTML_TTL", "600"))   # 静态页缓存 10 分钟
CACHE_API_TTL = int(os.getenv("HUNAN_CACHE_API_TTL", "60"))      # 实时接口缓存 60 秒
REQUEST_TIMEOUT = float(os.getenv("HUNAN_REQUEST_TIMEOUT", "15"))
RETRY_TIMES = int(os.getenv("HUNAN_RETRY_TIMES", "2"))

# ---- 政务栏目表（2026-08-27 实测） ----
# mode: html=服务端静态列表(分页 {template}_N.html)；api=JS动态加载，走湖南政务统一检索接口
#   POST https://api.hunan.gov.cn/search/common/search/{api_id}，body 见 web_crawler
# api_ids: api 模式的栏目频道 id（list_tyxx.html 页面内 channelId）
CHANNELS: dict[str, dict] = {
    "notice": {"mode": "api", "api_ids": [97434, 97433], "name": "通知公告(公告/通知)"},
    "eia_accept": {"mode": "html", "path": "xxgk/xzgs/jsxm/hpgs/jsslgk", "template": "index", "name": "环评公示-受理"},
    "eia_review": {"mode": "html", "path": "xxgk/xzgs/jsxm/hpgs/spyjgk_2", "template": "index", "name": "环评公示-拟审批"},
    "eia_decision": {"mode": "html", "path": "xxgk/xzgs/jsxm/hpgs/spjdgk_2", "template": "index", "name": "环评公示-审批决定"},
    "radiation_accept": {"mode": "html", "path": "xxgk/xzgs/fsxm/hfshp/slqkgk_2", "template": "index", "name": "辐射项目公示-受理"},
    "other_publicity": {"mode": "html", "path": "xxgk/xzgs/gfxm", "template": "list_xzgsx", "name": "其他公示(危废许可等)"},
    "policy": {"mode": "html", "path": "xxgk/zcfg/gfxwj", "template": "list_sy3", "name": "规范性文件"},
    "policy_interpret": {"mode": "html", "path": "xxgk/zcfg/zcfgjd", "template": "list_sy3", "name": "政策解读"},
    "env_quality_monthly": {"mode": "html", "path": "xxgk/zdly/hjjc/hjzl", "template": "index", "name": "环境质量月报"},
    "env_statistics": {"mode": "html", "path": "xxgk/zdly/hjjc/hjtj", "template": "index", "name": "环境统计年报"},
    "enforcement": {"mode": "html", "path": "xxgk/zdly/jdzf/ajcc", "template": "index", "name": "行政执法事后公开"},
    "credit_evaluation": {"mode": "html", "path": "xxgk/zdly/wrfz/qyhjxypj", "template": "index", "name": "企业环保信用评价"},
    "water_pollution": {"mode": "html", "path": "xxgk/zdly/wrfz/swrfz", "template": "index", "name": "水污染防治"},
    "budget_finance": {"mode": "html", "path": "xxgk/ghcw/czxx/czyjs", "template": "index", "name": "财政预决算"},
    "proposal_reply": {"mode": "html", "path": "xxgk/zwxxgk/jyta/srdjydf", "template": "index", "name": "建议提案"},
    "org_profile": {"mode": "html", "path": "xxgk/jgzn/jggk", "template": "index", "name": "机构概况"},
    # ---- P0 扩展（2026-08-27 全站穿透实测）----
    "news_zxdt": {"mode": "api", "api_ids": [97427], "name": "新闻动态-环保动态"},
    "news_hjyw": {"mode": "api", "api_ids": [97429], "name": "新闻动态-环境要闻"},
    "news_szxw": {"mode": "api", "api_ids": [97428], "name": "新闻动态-市州新闻"},
    "news_c101666": {"mode": "api", "api_ids": ["595581e6f0bb4e04b34d5fb1eb9c59f1"], "name": "新闻动态-时政关注"},
    "news_tpxw": {"mode": "api", "api_ids": [97430], "name": "新闻动态-图片新闻"},
    "survey_topic": {"mode": "html", "path": "hdjl/dczj/dczjzt", "template": "index", "name": "互动交流-调查征集主题"},
    "survey_feedback": {"mode": "html", "path": "hdjl/dczj/jgfk", "template": "index", "name": "互动交流-调查征集反馈"},
    "online_interview": {"mode": "html", "path": "hdjl/zxft", "template": "index", "name": "互动交流-在线访谈"},
    "nuclear_radiation": {"mode": "html", "path": "xxgk/zdly/hyfs", "template": "index", "name": "重点领域-核与辐射"},
    "eia_field": {"mode": "html", "path": "xxgk/zdly/hjyxpj", "template": "index", "name": "重点领域-环境影响评价"},
    "emergency": {"mode": "html", "path": "xxgk/zdly/yjgl", "template": "index", "name": "重点领域-应急管理"},
    "eco_protection": {"mode": "html", "path": "xxgk/zdly/stbh/stcj", "template": "index", "name": "重点领域-生态保护(示范创建)"},
    "soil_pollution": {"mode": "html", "path": "xxgk/zdly/wrfz/trwrfz", "template": "index", "name": "污染防治-土壤"},
    # ---- P1 扩展（2026-08-27 全站穿透实测）----
    "local_regulation": {"mode": "html", "path": "xxgk/zcfg/dfxfg", "template": "list_sy3", "name": "地方性法规"},
    "case_example": {"mode": "html", "path": "xxgk/zcfg/yasf", "template": "list_sy3", "name": "以案说法(以案释法)", "detail_pattern": r"(mp\.weixin\.qq\.com/s/|t\d{8}_\d+\.html)"},
    "enforce_supervision": {"mode": "html", "path": "xxgk/zdly/jdzf/zfgl", "template": "index", "name": "行政执法事前事中"},
    "special_fund": {"mode": "html", "path": "xxgk/ghcw/czxx/zxzjgl", "template": "index", "name": "专项资金管理"},
    "plan_program": {"mode": "html", "path": "xxgk/ghcw/ghjh", "template": "index", "name": "规划计划"},
    "proposal_cppcc": {"mode": "html", "path": "xxgk/zwxxgk/jyta/szxtadf", "template": "index", "name": "政协提案答复"},
    "annual_report": {"mode": "api", "api_ids": [85118], "name": "信息公开年报"},
    "complaint_report": {"mode": "html", "path": "xxgk/tsjbqk", "template": "index", "name": "投诉举报情况"},
    # ---- P2 机构静态信息（2026-08-27 全站穿透实测）----
    "org_leader": {"mode": "html", "path": "xxgk/jgld", "template": "index", "name": "机构信息-机构领导"},
    "org_depart": {"mode": "html", "path": "xxgk/jgzn/nsjg", "template": "index", "name": "机构信息-内设机构"},
    "org_unit": {"mode": "html", "path": "xxgk/jgzn/zsjg", "template": "index", "name": "机构信息-直属机构"},
    "hr_info": {"mode": "html", "path": "xxgk/rsjy/rsxx", "template": "index", "name": "人事教育-人事信息"},
    # ---- P3 媒体/互动（2026-08-27 全站穿透实测）----
    "media_video": {"mode": "html", "path": "tslm/hbsp", "template": "index", "name": "特色栏目-环保视频"},
    "media_press": {"mode": "html", "path": "tslm/xwfbh", "template": "index", "name": "特色栏目-新闻发布会"},
    "media_qa": {"mode": "html", "path": "tslm/hbddc", "template": "index", "name": "特色栏目-新媒体问政"},
}

# 统一检索接口（list_tyxx 模板数据源）
SEARCH_API = "https://api.hunan.gov.cn/search/common/search"

# 详情页 URL 特征：t{YYYYMMDD}_{id}.html
DETAIL_RE_PATTERN = r"t\d{8}_\d+\.html"
# 附件特征：files/xxx.pdf|xlsx|doc|docx
ATTACH_RE_PATTERN = r"/files/[0-9a-f]{32}\.(?:pdf|xlsx?|docx?|zip|rar)"
