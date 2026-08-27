"""HTTP 会话封装：WebShield 会话 token 维护、限速、重试、缓存。"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Optional

import requests

from . import config


class Cache:
    """SQLite 轻量缓存，按 (method, url, body) 摘要为 key。"""

    def __init__(self, db_path: str | Path | None = None):
        self._lock = threading.RLock()
        self._path = str(db_path or Path(config.CACHE_DB).resolve())
        with self._lock:
            self._conn = sqlite3.connect(self._path, check_same_thread=False)
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS cache ("
                " key TEXT PRIMARY KEY,"
                " value TEXT NOT NULL,"
                " expire_at REAL NOT NULL)"
            )
            self._conn.commit()

    @staticmethod
    def _key(method: str, url: str, body: Any) -> str:
        raw = f"{method}|{url}|{json.dumps(body, ensure_ascii=False, sort_keys=True)}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def get(self, method: str, url: str, body: Any | None = None) -> Optional[str]:
        k = self._key(method, url, body)
        with self._lock:
            row = self._conn.execute(
                "SELECT value, expire_at FROM cache WHERE key=?", (k,)
            ).fetchone()
        if not row:
            return None
        value, expire_at = row
        if expire_at < time.time():
            with self._lock:
                self._conn.execute("DELETE FROM cache WHERE key=?", (k,))
                self._conn.commit()
            return None
        return value

    def set(self, method: str, url: str, body: Any | None, value: str, ttl: float = config.CACHE_TTL) -> None:
        k = self._key(method, url, body)
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO cache (key, value, expire_at) VALUES (?,?,?)",
                (k, value, time.time() + ttl),
            )
            self._conn.commit()

    def clear(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM cache")
            self._conn.commit()


class PermitClient:
    """平台 HTTP 客户端：自动预热会话（WebShield）、限速、重试、可选缓存。"""

    def __init__(self, use_cache: bool = True, cache_db: str | None = None,
                 interval: float = config.REQUEST_INTERVAL):
        self.session = requests.Session()
        self.session.headers.update(config.DEFAULT_HEADERS)
        self._last_ts = 0.0
        self._lock = threading.RLock()
        self.interval = interval
        self.cache: Cache | None = Cache(cache_db) if use_cache else None
        self._ready = False

    # ---- 会话预热 ----
    def _ensure_ready(self) -> None:
        """访问首页获取并维护 WebShieldDRSessionVerify 会话 token。"""
        if self._ready:
            return
        with self._lock:
            if self._ready:
                return
            try:
                self._throttle()
                self.session.get(config.URL_HOME, timeout=config.TIMEOUT)
                self._ready = True
            except requests.RequestException:
                # 预热失败不阻塞：部分接口无 token 也可访问
                self._ready = True

    def _throttle(self) -> None:
        with self._lock:
            wait = self.interval - (time.time() - self._last_ts)
            if wait > 0:
                time.sleep(wait)
            self._last_ts = time.time()

    # ---- 核心请求 ----
    def request(self, method: str, url: str, params: dict | None = None,
                data: dict | None = None, use_cache: bool = True) -> str:
        self._ensure_ready()
        body = {"params": params, "data": data}

        if use_cache and self.cache:
            hit = self.cache.get(method, url, body)
            if hit is not None:
                return hit

        last_err: Optional[Exception] = None
        for attempt in range(config.RETRY_TIMES):
            try:
                self._throttle()
                resp = self.session.request(
                    method, url, params=params, data=data, timeout=config.TIMEOUT
                )
                resp.raise_for_status()
                resp.encoding = resp.apparent_encoding or resp.encoding
                text = resp.text
                if use_cache and self.cache:
                    self.cache.set(method, url, body, text)
                return text
            except requests.RequestException as e:  # noqa: PERF203
                last_err = e
                if attempt < config.RETRY_TIMES - 1:
                    time.sleep(config.RETRY_BACKOFF * (attempt + 1))
        raise RuntimeError(f"请求失败 {method} {url}: {last_err}")

    def get(self, url: str, params: dict | None = None, use_cache: bool = True) -> str:
        return self.request("GET", url, params=params, use_cache=use_cache)

    def post(self, url: str, data: dict | None = None, use_cache: bool = True) -> str:
        return self.request("POST", url, data=data, use_cache=use_cache)

    def download(self, url: str, params: dict | None = None) -> bytes:
        """下载二进制文件（不缓存）。"""
        self._ensure_ready()
        last_err: Optional[Exception] = None
        for attempt in range(config.RETRY_TIMES):
            try:
                self._throttle()
                resp = self.session.get(url, params=params, timeout=config.TIMEOUT * 2)
                resp.raise_for_status()
                return resp.content
            except requests.RequestException as e:  # noqa: PERF203
                last_err = e
                if attempt < config.RETRY_TIMES - 1:
                    time.sleep(config.RETRY_BACKOFF * (attempt + 1))
        raise RuntimeError(f"下载失败 {url}: {last_err}")
