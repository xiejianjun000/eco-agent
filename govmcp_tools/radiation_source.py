#!/usr/bin/env python3
"""
govmcp_tools.radiation_source — 全国辐射环境监测真实数据源
============================================================
直连生态环境部辐射环境监测技术中心（rmtc.org.cn）全国空气吸收剂量率
发布系统（data.rmtc.org.cn/gis/），官方公开数据免 key。1h 缓存。
（自 govmcp_tools 包真实重建：原 _scripts/radiation-mcp.py 独立服务保留）
"""

from __future__ import annotations

import re
import threading
import time
import urllib.request
from typing import Any

_BASE = "https://data.rmtc.org.cn/gis/"

_HEADERS = {"User-Agent": "Mozilla/5.0"}
_CACHE_TTL = 3600  # 1h

_province_cache: dict[str, Any] = {}
_station_cache: dict[str, Any] = {}
_cache_lock = threading.Lock()


def _http_get(path: str) -> str:
    req = urllib.request.Request(f"{_BASE}{path}", headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=25) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _radiation_provinces() -> list[dict[str, Any]]:
    """全国 31 省空气吸收剂量率实时汇总（省代表站 + 更新时间，nGy/h）。"""
    with _cache_lock:
        if _province_cache.get("ts", 0) > time.time() - _CACHE_TTL:
            return _province_cache["data"]
    html = _http_get("listtype0M.html")
    body = re.search(r"<body[^>]*>(.*)</body>", html, re.S)
    body = body.group(1) if body else html
    out: list[dict[str, Any]] = []
    for item in re.findall(r"<li class=\"datali\">(.*?)</li>", body, re.S):
        link = re.search(r'href="listsation0_(\d+)M\.html">\s*(.*?)\s*</a>', item, re.S)
        val = re.search(r'class="label">\s*([\d.]+)\s*nGy/h', item)
        t = re.search(r'class="showtime">\s*([\d-]+)', item)
        if link and val:
            label = link.group(2).strip()
            out.append(
                {
                    "province": label.split("(")[0].strip(),
                    "station": label.split("(")[1].rstrip(")").strip() if "(" in label else "",
                    "code": link.group(1),
                    "dose_rate_nGyh": float(val.group(1)),
                    "date": t.group(1) if t else "",
                }
            )
    with _cache_lock:
        _province_cache["ts"] = time.time()
        _province_cache["data"] = out
    return out


def _radiation_stations(province: str) -> list[dict[str, Any]]:
    """指定省份全部辐射监测站点明细（省代码如 43 或省份名如 湖南）。"""
    key = str(province).strip()
    with _cache_lock:
        if _station_cache.get(key, {}).get("ts", 0) > time.time() - _CACHE_TTL:
            return _station_cache[key]["data"]
    # 先找省份代码：省代表站列表里匹配（支持省份名或直接省代码）
    code = key if key.isdigit() else ""
    if not code:
        for p in _radiation_provinces():
            if key in p["province"] or key in p["station"]:
                code = p["code"]
                break
    if not code:
        raise ValueError(f"未匹配到省份: {province}")
    html = _http_get(f"listsation0_{code}M.html")
    body = re.search(r"<body[^>]*>(.*)</body>", html, re.S)
    body = body.group(1) if body else html
    out: list[dict[str, Any]] = []
    for item in re.findall(r"<li class=\"datali\">(.*?)</li>", body, re.S):
        name = re.search(r'<div class="divname">\s*(.*?)\s*</div>', item, re.S)
        val = re.search(r'class="label">\s*([\d.]+)\s*nGy/h', item)
        t = re.search(r'class="showtime">\s*([\d-]+)', item)
        if name and val:
            out.append(
                {
                    "station": name.group(1).strip(),
                    "dose_rate_nGyh": float(val.group(1)),
                    "date": t.group(1) if t else "",
                }
            )
    if not out:
        raise ValueError(f"省份 '{province}' 暂无站点数据")
    with _cache_lock:
        _station_cache[key] = {"ts": time.time(), "data": out}
    return out


def radiation_provinces() -> dict[str, Any]:
    return {
        "count": len(_radiation_provinces()),
        "provinces": _radiation_provinces(),
        "unit": "nGy/h",
        "source": "data.rmtc.org.cn（生态环境部辐射环境监测技术中心）",
        "note": "国家辐射环境监测网自动监测数据公开范围为国家/省级自动站；请勿据此推断个人剂量。",
    }


def radiation_stations(province: str) -> dict[str, Any]:
    return {
        "province": province,
        "stations": _radiation_stations(province),
        "unit": "nGy/h",
        "source": "data.rmtc.org.cn（生态环境部辐射环境监测技术中心）",
    }


def radiation_baseline() -> dict[str, Any]:
    return {
        "reference": "全国环境天然贯穿辐射剂量率本底水平一般 < 100 nGy/h；国家辐射环境监测网数据正常波动范围与往年相当。",
        "alert_threshold": "若出现连续明显升高（显著偏离本底并持续），以生态环境部及当地政府发布信息为准。",
        "unit": "nGy/h",
        "source": "《辐射环境监测技术规范》/ 生态环境部公开口径",
    }
