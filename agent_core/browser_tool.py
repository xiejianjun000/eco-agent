#!/usr/bin/env python3
"""
agent_core/browser_tool.py — 浏览器驱动工具（对标 Hermes 内置浏览器）
====================================================================
能力：
  - open(url)：打开页面取 title + 可见文本（真渲染优先，轻量抓取兜底）
  - fetch_text(url)：正文/纯文本提取（ReAct 内只读浏览用）
  - screenshot(url, out_path)：页面截图（仅真实浏览器驱动可用）

驱动策略（playwright 可选接入）：
  1. 若环境安装了 playwright + chromium → 真渲染（JS 动态内容/截图/多页）
  2. 否则自动降级 urllib 只读抓取（driver=httpx-fallback），返回 HTML→文本；
     截图类操作在降级态明确返回不可用，绝不伪装成功。

无第三方强依赖；网络受限/无 GUI 容器可正常闭环（降级路径）。
"""

from __future__ import annotations

import html
import importlib.util
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Optional

TIMEOUT = 12
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
MAX_TEXT = 8000

_URL_RE = re.compile(r"^https?://", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_STYLE_RE = re.compile(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>")


def _playwright_available() -> bool:
    try:
        return importlib.util.find_spec("playwright") is not None
    except Exception:
        return False


def _norm_url(url: str) -> str:
    url = url.strip()
    if not _URL_RE.match(url):
        url = "https://" + url
    return url


def _urllib_fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        raw = r.read()
    # 优先按响应头编码解码
    ctype = r.headers.get("Content-Type", "")
    enc = "utf-8"
    m = re.search(r"charset=([\w-]+)", ctype, re.I)
    if m:
        enc = m.group(1)
    return raw.decode(enc, errors="replace")


def _html_to_text(page: str) -> str:
    page = _SCRIPT_STYLE_RE.sub(" ", page)
    page = re.sub(r"(?is)<!--.*?-->", " ", page)
    # 保留块级换行
    page = re.sub(r"(?i)</(p|div|li|h[1-6]|tr|br|section|article)>", "\n", page)
    text = html.unescape(_TAG_RE.sub("", page))
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in text.splitlines()]
    out = "\n".join(ln for ln in lines if ln)
    return out[:MAX_TEXT]


def _extract_title(page: str) -> Optional[str]:
    m = re.search(r"(?is)<title[^>]*>(.*?)</title>", page)
    if m:
        return html.unescape(m.group(1)).strip()[:200]
    m = re.search(r'(?is)<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']', page)
    if m:
        return html.unescape(m.group(1)).strip()[:200]
    return None


class BrowserTool:
    """浏览器工具封装：open / fetch_text / screenshot。"""

    def __init__(self, timeout: int = TIMEOUT):
        self.timeout = timeout
        self._pw = None

    # ── driver 探测 ──────────────────────────────────────────────
    @property
    def driver(self) -> str:
        return "playwright" if _playwright_available() else "httpx-fallback"

    def _pw_sync(self):
        """惰性初始化 playwright 同步 API（可用时）。"""
        if self._pw is None and _playwright_available():
            try:
                from playwright.sync_api import sync_playwright

                self._pw = sync_playwright().start()
            except Exception:
                self._pw = False
        return self._pw or None

    # ── 打开页面（真渲染优先，抓取兜底）──────────────────────────
    def open(self, url: str, wait_ms: int = 800) -> dict:
        url = _norm_url(url)
        pw = self._pw_sync()
        if pw is not None:
            try:
                browser = pw.chromium.launch(headless=True)
                try:
                    page = browser.new_page()
                    page.goto(url, timeout=self.timeout * 1000, wait_until="domcontentloaded")
                    page.wait_for_timeout(wait_ms)
                    title = page.title() or ""
                    text = page.inner_text("body")[:MAX_TEXT]
                    final_url = page.url
                    return {"ok": True, "driver": "playwright", "title": title, "url": final_url, "text": text}
                finally:
                    browser.close()
            except Exception as exc:
                # playwright 启动/导航失败 → 降级只读抓取，不误导
                try:
                    page = _urllib_fetch(url)
                    return {
                        "ok": True,
                        "driver": "httpx-fallback",
                        "title": _extract_title(page) or "",
                        "url": url,
                        "text": _html_to_text(page),
                        "note": f"playwright 不可用/失败({exc})，已降级只读抓取",
                    }
                except Exception as exc2:
                    return {"ok": False, "driver": "playwright", "error": f"playwright 失败: {exc}；抓取兜底也失败: {exc2}"}
        try:
            page = _urllib_fetch(url)
            return {
                "ok": True,
                "driver": "httpx-fallback",
                "title": _extract_title(page) or "",
                "url": url,
                "text": _html_to_text(page),
            }
        except Exception as exc:
            return {"ok": False, "driver": "httpx-fallback", "error": str(exc)}

    # ── 只读正文提取 ─────────────────────────────────────────────
    def fetch_text(self, url: str) -> dict:
        url = _norm_url(url)
        try:
            page = _urllib_fetch(url)
            return {
                "ok": True,
                "driver": "httpx-fallback",
                "title": _extract_title(page) or "",
                "url": url,
                "text": _html_to_text(page),
            }
        except Exception as exc:
            return {"ok": False, "driver": "httpx-fallback", "error": str(exc)}

    # ── 截图（仅真实浏览器驱动）──────────────────────────────────
    def screenshot(self, url: str, out_path: str) -> dict:
        url = _norm_url(url)
        pw = self._pw_sync()
        if pw is None:
            return {
                "ok": False,
                "driver": "httpx-fallback",
                "error": "截图需要 playwright + chromium（当前未安装）。"
                "可 pip install playwright && playwright install chromium",
            }
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        try:
            browser = pw.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport={"width": 1280, "height": 900})
                page.goto(url, timeout=self.timeout * 1000, wait_until="domcontentloaded")
                page.wait_for_timeout(1200)
                page.screenshot(path=str(out), full_page=False)
                return {
                    "ok": True,
                    "driver": "playwright",
                    "path": str(out),
                    "bytes": out.stat().st_size if out.exists() else 0,
                }
            finally:
                browser.close()
        except Exception as exc:
            return {"ok": False, "driver": "playwright", "error": str(exc)}

    # ── ReAct 工具接线 ───────────────────────────────────────────
    def register_into_react(self, react: Any) -> None:
        """将 browser_* 工具挂进 ReAct++（与 mcp_connector 接线方式一致）。"""
        react.register_tool(
            "browser_open",
            lambda url: self.open(url),
            "浏览器打开网页：返回页面标题与可见文本（真实渲染优先，受限时自动降级只读抓取）",
        )
        react.register_tool(
            "browser_fetch_text", lambda url: self.fetch_text(url), "只读抓取网页正文文本（无需浏览器渲染；适合快速浏览静态页）"
        )
        react.register_tool(
            "browser_screenshot",
            lambda url, path="": self.screenshot(url, path),
            "浏览器截图保存为 PNG（需要 playwright + chromium；参数: url, 输出路径）",
        )


_DEFAULT: Optional[BrowserTool] = None


def get_browser() -> BrowserTool:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = BrowserTool()
    return _DEFAULT


def register_into_react(react: Any) -> None:
    """便捷入口：eco.browser = get_browser() + register_into_react。"""
    get_browser().register_into_react(react)
