"""大气环境领域：实时空气质量、预报、城市月报。"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# 全国城市空气质量实时发布平台（监测总站）
AIR_PLATFORM = "https://air.cnemc.cn:18007/"
AIR_FORECAST = "http://106.37.208.228:8082/"
# 第三方国控站实时接口（非官方，仅作解析来源，标注来源）
THIRD_PARTY_PM_API = "http://eia-data.com/getpmnow/"

CITY_ALIAS = {
    "北京": "beijing", "上海": "shanghai", "广州": "guangzhou", "深圳": "shenzhen",
    "天津": "tianjin", "重庆": "chongqing", "成都": "chengdu", "杭州": "hangzhou",
    "南京": "nanjing", "武汉": "wuhan", "西安": "xian", "苏州": "suzhou",
}


def read_air_quality(fetcher, cache, city: str) -> dict:
    """查询城市实时空气质量（AQI 与六项污染物）。来源：全国城市空气质量实时发布平台。"""
    key = f"air:realtime:{city}"
    cached = cache.get(key)
    if cached:
        return {**cached, "cache": "hit"}

    result = {"city": city, "source": AIR_PLATFORM, "items": [], "note": ""}
    # 尝试第三方结构化接口（非官方）
    try:
        payload = fetcher.get_json(THIRD_PARTY_PM_API)
        data = payload.get("data") or payload.get("result") or []
        alias = CITY_ALIAS.get(city, city.lower())
        for row in data:
            name = str(row.get("city") or row.get("name") or "").lower()
            if alias in name or city in str(row.get("city") or ""):
                result["items"] = [{
                    "city": row.get("city"), "aqi": row.get("aqi"),
                    "pm25": row.get("pm2_5") or row.get("pm25"), "pm10": row.get("pm10"),
                    "so2": row.get("so2"), "no2": row.get("no2"), "co": row.get("co"),
                    "o3": row.get("o3"), "level": row.get("level") or row.get("quality"),
                    "updated": row.get("time") or row.get("updated"),
                }]
                break
        if result["items"]:
            result["source"] = f"{AIR_PLATFORM} (经第三方接口 eia-data.com)"
            result["note"] = "第三方接口源自监测总站国控站数据，非官方授权，仅供参考"
            cache.set(key, result, ttl=300)
            return result
    except Exception as exc:  # noqa: BLE001
        logger.debug("第三方空气质量接口不可用: %s", exc)

    # 降级：抓取官方平台页面概览
    try:
        html = fetcher.get_text(AIR_PLATFORM)
        result["note"] = "官方平台为动态页面，未能解析结构化数据；建议后续接入 Playwright 浏览器抓取"
        result["page_snippet"] = html[:2000]
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)
    cache.set(key, result, ttl=300)
    return result


def read_air_forecast(fetcher, cache, region: str = "全国") -> dict:
    """读取空气质量预报（会商结果/区域预报）。来源：全国空气质量预报平台。"""
    key = f"air:forecast:{region}"
    cached = cache.get(key)
    if cached:
        return {**cached, "cache": "hit"}
    result = {"region": region, "source": AIR_FORECAST, "content": "", "note": ""}
    try:
        html = fetcher.get_text(AIR_FORECAST)
        from ..core.parser import parse_article
        text = parse_article(html, max_chars=4000)
        if text:
            result["content"] = text
        else:
            result["note"] = "预报平台为动态页面，未提取到文本；建议升级浏览器抓取"
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)
    cache.set(key, result, ttl=1800, slow=True)
    return result


def read_air_monthly(fetcher, cache, month: str | None = None) -> dict:
    """读取全国环境空气质量状况月报（主站环境质量栏目）。"""
    key = f"air:monthly:{month or 'latest'}"
    cached = cache.get(key)
    if cached:
        return {**cached, "cache": "hit"}
    url = "https://www.mee.gov.cn/hjzl/dqhj/" if not month else "https://www.mee.gov.cn/hjzl/dqhj/"
    result = {"month": month or "最新", "source": url, "links": []}
    try:
        html = fetcher.get_text(url)
        from ..core.parser import parse_links
        links = parse_links(html, base_url=url, limit=30)
        if month:
            kw = month.replace("-", "").replace("年", "").replace("月", "")
            links = [lk for lk in links if kw in lk["title"]][:5]
        result["links"] = links[:15]
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)
    cache.set(key, result, ttl=3600, slow=True)
    return result
