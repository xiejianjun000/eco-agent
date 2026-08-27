"""下载工具族：任意 URL 下载、限流、防穿越、大小限制。"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from .fetcher import Fetcher
from .parser import safe_filename
from .utils import ensure_within, get_download_base

logger = logging.getLogger(__name__)


class Downloader:
    """安全的下载器：仅 http/https、限大小、限目录。"""

    def __init__(self, fetcher: Fetcher, base_dir: Optional[Path] = None, max_size_mb: int = 200) -> None:
        self._fetcher = fetcher
        self._base = base_dir or get_download_base({})
        self._base.mkdir(parents=True, exist_ok=True)
        self._max_bytes = max_size_mb * 1024 * 1024

    def download(self, url: str, save_dir: str = ".", filename: Optional[str] = None, sub_dir: Optional[str] = None) -> dict:
        """下载 URL 到下载根目录。save_dir 相对下载根目录；sub_dir 追加一层。"""
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"仅支持 http/https 下载，拒绝: {url}")

        target_root = self._base
        if sub_dir:
            target_root = ensure_within(self._base, Path(sub_dir))
            target_root.mkdir(parents=True, exist_ok=True)

        rel_dir = ensure_within(self._base, Path(save_dir or "."))
        rel_dir.mkdir(parents=True, exist_ok=True)

        name = filename or safe_filename(Path(parsed.path).name) or "download.bin"
        dest = ensure_within(rel_dir, Path(name))

        content = self._fetcher.get_bytes(url)
        if len(content) > self._max_bytes:
            raise ValueError(f"文件超过大小限制({self._max_bytes // (1024 * 1024)}MB): {len(content)} bytes")

        dest.write_bytes(content)
        return {
            "url": url,
            "filename": name,
            "path": str(dest),
            "size_bytes": len(content),
            "saved_at": str(dest),
        }

    def download_text(self, text: str, filename: str, save_dir: str = ".", sub_dir: Optional[str] = None) -> dict:
        """将文本内容写入文件（数据导出用）。"""
        target_root = self._base
        if sub_dir:
            target_root = ensure_within(self._base, Path(sub_dir))
            target_root.mkdir(parents=True, exist_ok=True)
        rel_dir = ensure_within(self._base, Path(save_dir or "."))
        rel_dir.mkdir(parents=True, exist_ok=True)
        dest = ensure_within(rel_dir, Path(safe_filename(filename)))
        dest.write_text(text, encoding="utf-8")
        return {"filename": dest.name, "path": str(dest), "size_bytes": len(text.encode("utf-8"))}
