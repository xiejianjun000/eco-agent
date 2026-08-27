"""湖南省环境质量实时数据 API 封装（hn.leitesoft.cn:9020 HNAirWebAPI）。

探明流程（2026-08-27）：
1. GET /MobileApp/AuthenticationLogin?userName=hnapp&password=xxx  → 返回 data=token
2. 后续请求携带 Authorization: Bearer <token>
3. 响应体是 JSON 字符串（部分接口需二次 parseJSON），字段为英文。

凭据不内置：HUNAN_AIR_API_PASSWORD 需从官网首页底部 iframe
（https://hn.leitesoft.cn:8031/HN/*.html）页面 JS 中提取后注入环境变量。
"""
from __future__ import annotations

import json
import logging
import threading
import time

from .. import config
from .http_client import fetch_json_text

logger = logging.getLogger(__name__)

TOKEN_TTL = 600  # 秒，token 有效期保守值，到期自动重新登录
_token: str | None = None
_token_ts: float = 0.0
_lock = threading.Lock()


def _login() -> str:
    global _token, _token_ts
    if not config.AIR_API_PASSWORD:
        raise RuntimeError(
            "未配置实时空气 API 凭据：请设置环境变量 HUNAN_AIR_API_PASSWORD"
            "（从官网首页 iframe 页面 JS 中提取），或使用 HUNAN_AIR_API_USER 覆盖账号。"
        )
    url = f"{config.AIR_API_BASE}/MobileApp/AuthenticationLogin"
    text = fetch_json_text(
        url,
        params={"userName": config.AIR_API_USER, "password": config.AIR_API_PASSWORD},
        use_cache=False,
    )
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:  # 部分实现返回非 JSON 包装
        raise RuntimeError(f"空气 API 登录响应解析失败: {text[:200]}") from exc
    token = data.get("data") or data.get("Data") or data.get("token")
    if not token:
        raise RuntimeError(f"空气 API 登录失败（请检查账号/密码）: {text[:200]}")
    _token, _token_ts = token, time.time()
    logger.info("空气 API 登录成功，token 已更新")
    return token


def _bearer_token() -> str:
    global _token, _token_ts
    with _lock:
        if _token and time.time() - _token_ts < TOKEN_TTL:
            return _token
        return _login()


def _api_get(path: str, params: dict | None = None) -> list | dict:
    url = f"{config.AIR_API_BASE}/{path}"
    headers = {"Authorization": f"Bearer {_bearer_token()}"}
    text = fetch_json_text(url, params=params, headers=headers)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw": text}


def _normalize_rows(data: list | dict) -> list[dict]:
    """兼容响应为 list 或 {"data": [...]} 两种结构。"""
    if isinstance(data, list):
        return [d for d in data if isinstance(d, dict)]
    if isinstance(data, dict):
        inner = data.get("data") or data.get("Data") or data.get("rows") or data.get("result")
        if isinstance(inner, list):
            return [d for d in inner if isinstance(d, dict)]
        return []
    return []


def air_realtime(region: str | None = None) -> list[dict]:
    """14 市州 + 全省实时 AQI。region 可传市州名（如 长沙/株洲）或 全省。"""
    rows = _normalize_rows(_api_get("MobileApp/GetSortNow", {"stationType": "STCenter"}))
    if region:
        rows = [r for r in rows if region in str(r.get("StationName") or r.get("stationName") or "")]
    return rows


def air_hourly(city: str, order_by: str = "ASC") -> list[dict]:
    """指定城市逐小时空气质量序列。"""
    if not city:
        raise ValueError("city 为必填参数")
    rows = _normalize_rows(
        _api_get("MobileApp/GetCurHourlyByCity", {"city": city, "orderBy": order_by})
    )
    return rows


def air_forecast() -> list[dict]:
    """最新一期城市空气质量预报/预警。"""
    return _normalize_rows(_api_get("PublishData/GeNewTimetForcastMost"))


def air_rank_daily(begin_date: str, end_date: str) -> list[dict]:
    """按日城市空气质量排名。日期格式 YYYY-MM-DD。"""
    _DATE_RE = __import__("re").compile(r"\d{4}-\d{2}-\d{2}")
    for d, f in ((begin_date, "begin_date"), (end_date, "end_date")):
        if not _DATE_RE.fullmatch(d or ""):
            raise ValueError(f"{f} 格式应为 YYYY-MM-DD，收到: {d!r}")
    if begin_date > end_date:
        raise ValueError(f"begin_date 不能晚于 end_date: {begin_date} > {end_date}")
    return _normalize_rows(
        _api_get(
            "MobileApp/GetSortDaily",
            {"choiceType": "isCity", "dataType": "0", "beginTime": begin_date, "endTime": end_date},
        )
    )
