#!/usr/bin/env python3
"""
govmcp.tools.government.cnemc — 中国环境监测总站(CNEMC)实时空气质量客户端

直连"全国城市空气质量实时发布平台"(https://air.cnemc.cn:18007)公开 JSON 接口，
获取全国地市级城市实时 6 参数(PM2.5/PM10/SO2/NO2/CO/O3) + AQI + 首要污染物。

特性:
- httpx 同步客户端, 10s 超时, 最多 2 次重试
- 30 分钟 TTL 内存缓存, 避免频繁请求官方平台
- 失败降级: 返回最近一次成功缓存并标注 data_source="cache"; 无缓存时抛错
- 城市级数据按 GB 3095-2012 由站点均值计算 IAQI/AQI
"""

from __future__ import annotations

import statistics
import threading
import time
from typing import Any

import httpx

CNEMC_REALTIME_URL = "https://air.cnemc.cn:18007/HourChangesPublish/GetAllAQIPublishLive"

_REQUEST_HEADERS = {
    "Accept": "*/*",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Origin": "https://air.cnemc.cn:18007",
    "Referer": "https://air.cnemc.cn:18007/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "X-Requested-With": "XMLHttpRequest",
}

REQUEST_TIMEOUT = 10.0  # 秒
MAX_RETRIES = 2  # 重试次数(首次请求外)
CACHE_TTL = 30 * 60  # 30 分钟

_cache_lock = threading.Lock()
_cache_data: list[dict[str, Any]] | None = None
_cache_time: float | None = None  # 最近一次成功获取的时间戳


class CNEMCError(RuntimeError):
    """CNEMC 数据获取失败(且无可用缓存)。"""


def _fetch_all_stations() -> tuple[list[dict[str, Any]], float, bool]:
    """
    获取全国站点实时数据。

    Returns:
        (站点记录列表, 数据时间戳, 是否来自缓存降级)

    Raises:
        CNEMCError: 请求失败且无缓存可用
    """
    global _cache_data, _cache_time
    with _cache_lock:
        if _cache_data is not None and _cache_time is not None:
            if time.time() - _cache_time < CACHE_TTL:
                return _cache_data, _cache_time, False

    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            with httpx.Client(timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
                resp = client.post(
                    CNEMC_REALTIME_URL, content=b"", headers=_REQUEST_HEADERS
                )
                resp.raise_for_status()
                data = resp.json()
            if not isinstance(data, list) or not data:
                raise CNEMCError(f"CNEMC 返回数据格式异常: {str(data)[:200]}")
            with _cache_lock:
                _cache_data = data
                _cache_time = time.time()
            return data, _cache_time, False
        except Exception as exc:  # noqa: BLE001 - 统一降级处理
            last_exc = exc
            if attempt < MAX_RETRIES:
                time.sleep(1.0 * (attempt + 1))

    # 全部重试失败 -> 缓存降级
    with _cache_lock:
        if _cache_data is not None and _cache_time is not None:
            return _cache_data, _cache_time, True
    raise CNEMCError(
        f"无法连接中国环境监测总站实时发布平台(已重试 {MAX_RETRIES} 次): {last_exc}; "
        "且无历史缓存可降级。请稍后重试, 本工具不会返回虚构数据。"
    )


def _normalize_city(name: str) -> str:
    """城市名归一化: 去掉常见后缀, 便于模糊匹配。"""
    name = (name or "").strip()
    for suffix in ("市", "地区", "盟", "自治州", "藏族自治州", "自治县", "省"):
        if name.endswith(suffix) and len(name) > len(suffix):
            name = name[: -len(suffix)]
            break
    return name


def _match_city(records: list[dict[str, Any]], city: str) -> list[dict[str, Any]]:
    """按城市名模糊匹配站点记录(如 "娄底"/"娄底市" 均可)。"""
    target = _normalize_city(city)
    if not target:
        return []
    matched = []
    for rec in records:
        area = _normalize_city(str(rec.get("Area", "")))
        if area and (target in area or area in target):
            matched.append(rec)
    return matched


# GB 3095-2012 24h/8h 浓度分指数(IAQI)断点表: (浓度断点, IAQI 断点)
_IAQI_TABLE = {
    "pm25": [0, 35, 75, 115, 150, 250, 350, 500],
    "pm10": [0, 50, 150, 250, 350, 420, 500, 600],
    "so2": [0, 50, 150, 475, 800, 1600, 2100, 2620],
    "no2": [0, 40, 80, 180, 280, 565, 750, 940],
    "co": [0, 2, 4, 14, 24, 36, 48, 60],  # mg/m3
    "o3_8h": [0, 100, 160, 215, 265, 800, 800, 800],
}
_IAQI_VALUES = [0, 50, 100, 150, 200, 300, 400, 500]
_POLLUTANT_LABELS = {
    "pm25": "PM2.5",
    "pm10": "PM10",
    "so2": "SO2",
    "no2": "NO2",
    "co": "CO",
    "o3_8h": "O3",
}


def _iaqi(pollutant: str, conc: float) -> float | None:
    """按分段线性插值计算单项污染物 IAQI。"""
    bp = _IAQI_TABLE[pollutant]
    if conc < 0:
        return None
    for i in range(len(bp) - 1):
        lo, hi = bp[i], bp[i + 1]
        if lo <= conc <= hi:
            if hi == lo:
                return float(_IAQI_VALUES[i + 1])
            ratio = (conc - lo) / (hi - lo)
            return _IAQI_VALUES[i] + ratio * (_IAQI_VALUES[i + 1] - _IAQI_VALUES[i])
    return 500.0


_AQI_LEVELS = [
    (50, "优"),
    (100, "良"),
    (150, "轻度污染"),
    (200, "中度污染"),
    (300, "重度污染"),
    (10**9, "严重污染"),
]


def _aqi_level(aqi: float) -> str:
    for limit, label in _AQI_LEVELS:
        if aqi <= limit:
            return label
    return "严重污染"


def _num(value: Any) -> float | None:
    """解析数值, "NA"/"—"/"" 等返回 None。"""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def get_city_realtime_air_quality(city: str) -> dict[str, Any]:
    """
    查询指定城市实时空气质量(CNEMC 官方数据)。

    Args:
        city: 城市名, 支持模糊匹配(如 "长沙"/"长沙市"/"娄底")

    Returns:
        包含 aqi/level/pm25/pm10/so2/no2/co/o3/main_pollutant/
        publish_time/data_source 等字段的字典

    Raises:
        CNEMCError: 平台不可达且无缓存, 或城市未匹配
    """
    records, fetched_at, from_cache = _fetch_all_stations()
    matched = _match_city(records, city)
    if not matched:
        raise CNEMCError(
            f"CNEMC 实时数据中未匹配到城市 '{city}', 请确认城市名(支持全国地市级城市)。"
        )

    # 城市级浓度 = 各站点滑动均值(24h / O3 8h)的算术平均
    field_map = {
        "pm25": "PM2_5_24h",
        "pm10": "PM10_24h",
        "so2": "SO2_24h",
        "no2": "NO2_24h",
        "co": "CO_24h",
        "o3_8h": "O3_8h_24h",
    }
    city_conc: dict[str, float] = {}
    for key, field in field_map.items():
        vals = [v for v in (_num(r.get(field)) for r in matched) if v is not None]
        if vals:
            city_conc[key] = statistics.fmean(vals)

    # 计算城市 AQI 与首要污染物
    iaqis = {k: _iaqi(k, v) for k, v in city_conc.items()}
    iaqis = {k: v for k, v in iaqis.items() if v is not None}
    aqi = round(max(iaqis.values())) if iaqis else None
    main_pollutant = "—"
    if aqi is not None and aqi > 50 and iaqis:
        top = max(iaqis, key=iaqis.get)
        main_pollutant = _POLLUTANT_LABELS[top]

    publish_times = [str(r.get("TimePointStr", "")) for r in matched]
    publish_time = max(publish_times) if publish_times else ""

    return {
        "city": matched[0].get("Area", city),
        "station_count": len(matched),
        "aqi": aqi,
        "level": _aqi_level(aqi) if aqi is not None else None,
        "pm25": round(city_conc["pm25"], 1) if "pm25" in city_conc else None,
        "pm10": round(city_conc["pm10"], 1) if "pm10" in city_conc else None,
        "so2": round(city_conc["so2"], 1) if "so2" in city_conc else None,
        "no2": round(city_conc["no2"], 1) if "no2" in city_conc else None,
        "co": round(city_conc["co"], 2) if "co" in city_conc else None,
        "o3": round(city_conc["o3_8h"], 1) if "o3_8h" in city_conc else None,
        "main_pollutant": main_pollutant,
        "publish_time": publish_time,
        "data_source": "cache" if from_cache else "cnemc_realtime",
        "cache_time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(fetched_at))
        if from_cache
        else None,
    }


def _reset_cache() -> None:
    """仅供测试使用: 清空缓存。"""
    global _cache_data, _cache_time
    with _cache_lock:
        _cache_data = None
        _cache_time = None
