#!/usr/bin/env python3
"""
govmcp_tools.weather_source — 气象真实数据源（中国天气网 + Open-Meteo）
==========================================================================
- 实时/预报：weather.com.cn 公开接口（101 城市码体系，气象局旗下）
- 历史归档：Open-Meteo archive（免费无 key，按内置经纬度）
（自 govmcp_tools 包真实重建：原 _scripts/weather-mcp.py 独立服务保留）
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from typing import Any

# 城市 → 101 代码表（湖南执法辖区优先，可扩展）
CITY_CODES = {
    "长沙": "101250101",
    "娄底": "101250801",
    "双峰": "101250802",
    "冷水江": "101250803",
    "涟源": "101250804",
    "新化": "101250805",
    "北京": "101010100",
    "广州": "101280101",
}

# 城市 → 经纬度（Open-Meteo 历史天气用）
CITY_COORDS = {
    "长沙": (28.20, 112.98),
    "娄底": (27.70, 111.99),
    "冷水江": (27.69, 111.44),
    "双峰": (27.46, 112.19),
    "涟源": (27.69, 111.67),
    "新化": (27.73, 111.33),
    "北京": (39.90, 116.41),
    "广州": (23.13, 113.26),
}

_BASE = "http://d1.weather.com.cn"
_HEADERS = {
    "Referer": "http://www.weather.com.cn/",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}


def _resolve_code(city: str) -> str:
    if re.fullmatch(r"101\d{6}", city):
        return city
    return CITY_CODES.get(city.strip(), "")


def _fetch(path: str) -> str:
    req = urllib.request.Request(f"{_BASE}{path}", headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=12) as resp:
        return resp.read().decode("utf-8", errors="replace")


def weather_now(city: str) -> dict[str, Any]:
    code = _resolve_code(city)
    if not code:
        return {"error": f"未知城市: {city}（可用 weather_city_list 查内置城市，或直接用 101 城市码）"}
    try:
        raw = _fetch(f"/sk_2d/{code}.html")
        m = re.search(r"dataSK=(\{.*?\})", raw)
        data = json.loads(m.group(1)) if m else {}
        if not data:
            return {"error": "天气数据解析失败", "city": city}
        return {
            "city": data.get("cityname", city),
            "code": data.get("city", code),
            "temp_c": data.get("temp"),
            "humidity": data.get("SD"),
            "wind_dir": data.get("WD"),
            "wind_level": data.get("WS"),
            "visibility_km": data.get("njd"),
            "pressure_hpa": data.get("qy"),
            "rain_mm": data.get("rain"),
            "rain24h_mm": data.get("rain24h"),
            "aqi": data.get("aqi"),
            "aqi_pm25": data.get("aqi_pm25"),
            "weather": data.get("weather"),
            "updated": data.get("date", "") + " " + data.get("time", ""),
        }
    except Exception as exc:  # noqa: BLE001
        return {"error": f"气象数据获取失败: {exc}", "city": city}


def weather_forecast(city: str) -> dict[str, Any]:
    code = _resolve_code(city)
    if not code:
        return {"error": f"未知城市: {city}"}
    try:
        raw = _fetch(f"/weather_index/{code}.html")
        m = re.search(r"cityDZ =(\{.*?\});", raw)
        data = json.loads(m.group(1)) if m else {}
        info = data.get("weatherinfo", {})
        return {
            "city": info.get("city", city),
            "code": code,
            "today": {
                "weather": info.get("weather"),
                "temp_high": info.get("temp"),
                "temp_low": info.get("tempn"),
                "wind": str(info.get("wd", "")) + " " + str(info.get("ws", "")),
            },
            "forecast_time": info.get("fctime", ""),
        }
    except Exception as exc:  # noqa: BLE001
        return {"error": f"预报获取失败: {exc}", "city": city}


def weather_history(city: str, start_date: str, end_date: str) -> dict[str, Any]:
    """历史天气（Open-Meteo archive，免费无 key）：执法气象佐证用。"""
    coords = CITY_COORDS.get(city.strip())
    if not coords:
        return {"error": f"未知城市: {city}（内置城市见 weather_city_list）"}
    try:
        lat, lon = coords
        params = urllib.parse.urlencode(
            {
                "latitude": lat,
                "longitude": lon,
                "start_date": start_date,
                "end_date": end_date,
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max",
                "timezone": "Asia/Shanghai",
            }
        )
        req = urllib.request.Request(
            f"https://archive-api.open-meteo.com/v1/archive?{params}", headers={"User-Agent": "eco-agent-govmcp-tools/1.0"}
        )
        with urllib.request.urlopen(req, timeout=25) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
        daily = raw.get("daily", {})
        days = []
        for i, date in enumerate(daily.get("time", [])):
            days.append(
                {
                    "date": date,
                    "temp_max_c": daily.get("temperature_2m_max", [None] * (i + 1))[i],
                    "temp_min_c": daily.get("temperature_2m_min", [None] * (i + 1))[i],
                    "precipitation_mm": daily.get("precipitation_sum", [None] * (i + 1))[i],
                    "wind_max_kmh": daily.get("wind_speed_10m_max", [None] * (i + 1))[i],
                }
            )
        return {"city": city, "lat": lat, "lon": lon, "source": "open-meteo-archive", "days": days}
    except Exception as exc:  # noqa: BLE001
        return {"error": f"历史天气获取失败: {exc}", "city": city}


def weather_city_list() -> dict[str, Any]:
    return {"count": len(CITY_CODES), "cities": CITY_CODES, "source": "中国天气网 101 城市码体系（内置湖南执法辖区优先）"}
