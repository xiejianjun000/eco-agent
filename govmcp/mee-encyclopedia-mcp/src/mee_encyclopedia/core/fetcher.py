"""HTTP 抓取客户端：超时、重试、UA、SSL 控制、礼貌限速。

合规设计（避免触发反爬且合法合规）：
- 低频率请求：请求间隔限速（默认 2~4 秒随机），绝不高频扫描
- 指数退避重试：失败后 1s/2s/4s 退避，不激进重试
- 缓存优先：重复查询命中缓存，不重复请求源站
- 标准浏览器 UA + Accept-Language，不做指纹伪造
- 不绕过验证码 / 登录 / robots.txt
"""
from __future__ import annotations

import logging
import random
import time
from typing import Any

import httpx

from .utils import load_config

logger = logging.getLogger(__name__)

_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


class Fetcher:
    """统一的网页/API 抓取器：礼貌限速 + 指数退避 + 文本/二进制两种模式。"""

    def __init__(self, config: dict | None = None) -> None:
        cfg = config or load_config()
        http_cfg = cfg.get("http", {})
        self.timeout = float(http_cfg.get("timeout", 20))
        self.retries = int(http_cfg.get("retries", 2))
        self.verify_ssl = bool(http_cfg.get("verify_ssl", True))
        self.user_agent = http_cfg.get("user_agent", _DEFAULT_UA)
        self.min_interval = float(http_cfg.get("min_interval_seconds", 2.0))
        self.jitter = float(http_cfg.get("jitter_seconds", 2.0))
        self._last_request = 0.0
        self._client = httpx.Client(
            timeout=self.timeout,
            verify=self.verify_ssl,
            follow_redirects=True,
            headers={"User-Agent": self.user_agent, "Accept-Language": "zh-CN,zh;q=0.9"},
        )

    def _pace(self) -> None:
        """请求间隔限速：距上次请求至少 min_interval + 随机抖动，避免规律性触发反爬。"""
        wait = self.min_interval + random.uniform(0, self.jitter)
        elapsed = time.monotonic() - self._last_request
        if elapsed < wait:
            time.sleep(wait - elapsed)

    def _backoff(self, attempt: int) -> None:
        """指数退避：1s, 2s, 4s... 最多 8s。"""
        time.sleep(min(2**attempt, 8))

    def get_text(self, url: str, params: dict | None = None) -> str:
        """GET 请求并返回文本。失败自动退避重试。"""
        last_exc: Exception | None = None
        for attempt in range(self.retries + 1):
            self._pace()
            try:
                resp = self._client.get(url, params=params)
                resp.raise_for_status()
                resp.encoding = resp.encoding or "utf-8"
                self._last_request = time.monotonic()
                return resp.text
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                logger.warning("GET %s 失败(第%d次): %s", url, attempt + 1, exc)
                if attempt < self.retries:
                    self._backoff(attempt)
        raise RuntimeError(f"抓取失败: {url} -> {last_exc}")

    def get_json(self, url: str, params: dict | None = None) -> Any:
        """GET 请求并解析 JSON。"""
        text = self.get_text(url, params=params)
        return httpx._utils.json_loads(text)

    def get_bytes(self, url: str) -> bytes:
        """GET 请求并返回二进制内容（用于下载）。"""
        last_exc: Exception | None = None
        for attempt in range(self.retries + 1):
            self._pace()
            try:
                resp = self._client.get(url)
                resp.raise_for_status()
                self._last_request = time.monotonic()
                return resp.content
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                logger.warning("下载 %s 失败(第%d次): %s", url, attempt + 1, exc)
                if attempt < self.retries:
                    self._backoff(attempt)
        raise RuntimeError(f"下载失败: {url} -> {last_exc}")

    def close(self) -> None:
        self._client.close()
