"""HTTP 客户端：模拟浏览器 TLS 指纹 + 全局限速 + 双层缓存 + 自动重试。

主站 sthjt.hunan.gov.cn 存在 TLS/HTTP2 指纹级 WAF（curl/requests 直连会被秒断），
因此统一使用 curl_cffi 的 impersonate="chrome" 模拟 Chrome 指纹访问。
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from typing import Any

from cachetools import TTLCache
from curl_cffi import requests as curl_requests

try:  # curl_cffi 不同版本的异常类位置不同
    from curl_cffi.requests.exceptions import RequestException as CurlRequestException
except ImportError:  # pragma: no cover
    from curl_cffi.requests.errors import RequestsError as CurlRequestException  # type: ignore

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_fixed,
)

from .. import config

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 "
    "hunan-env-mcp/0.1"
)


class RateLimiter:
    """令牌桶式限速器（全局单例）。"""

    def __init__(self, rps: float) -> None:
        self._interval = 1.0 / max(rps, 0.1)
        self._lock = threading.Lock()
        self._next_time = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            if self._next_time > now:
                time.sleep(self._next_time - now)
            self._next_time = time.monotonic() + self._interval


_limiter = RateLimiter(config.RATE_LIMIT_RPS)
_html_cache: TTLCache = TTLCache(maxsize=256, ttl=config.CACHE_HTML_TTL)
_api_cache: TTLCache = TTLCache(maxsize=128, ttl=config.CACHE_API_TTL)


def _cache_key(url: str, params: dict | None, headers: dict | None) -> str:
    raw = json.dumps(
        {
            "url": url,
            "params": params or {},
            "headers": {k: v for k, v in (headers or {}).items() if k.lower() != "authorization"},
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


@retry(
    retry=retry_if_exception_type((CurlRequestException, OSError)),
    stop=stop_after_attempt(config.RETRY_TIMES),
    wait=wait_fixed(1.0),
    reraise=True,
)
def _request(url: str, *, params: dict | None, headers: dict | None, timeout: float) -> str:
    _limiter.wait()
    resp = curl_requests.get(
        url,
        params=params,
        headers={"User-Agent": USER_AGENT, **(headers or {})},
        impersonate="chrome",
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.text


def fetch_html(url: str, params: dict | None = None, use_cache: bool = True) -> str:
    """抓取 HTML 文本（用于静态栏目页，缓存 10 分钟）。"""
    key = _cache_key(url, params, None)
    if use_cache and key in _html_cache:
        return _html_cache[key]
    text = _request(url, params=params, headers=None, timeout=config.REQUEST_TIMEOUT)
    if use_cache:
        _html_cache[key] = text
    return text


def fetch_json_text(
    url: str,
    params: dict | None = None,
    headers: dict | None = None,
    use_cache: bool = True,
) -> str:
    """抓取接口响应文本（用于实时空气 API，缓存 60 秒，不缓存 Authorization 差异）。"""
    key = _cache_key(url, params, headers)
    if use_cache and key in _api_cache:
        return _api_cache[key]
    text = _request(url, params=params, headers=headers, timeout=config.REQUEST_TIMEOUT)
    if use_cache:
        _api_cache[key] = text
    return text


def fetch_json(
    url: str,
    params: dict | None = None,
    headers: dict | None = None,
    use_cache: bool = True,
) -> Any:
    """抓取并解析 JSON。"""
    return json.loads(fetch_json_text(url, params=params, headers=headers, use_cache=use_cache))
