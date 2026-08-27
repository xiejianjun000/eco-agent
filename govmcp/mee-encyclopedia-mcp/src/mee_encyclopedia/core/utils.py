"""通用工具：配置加载、日志、审计、路径安全。"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any, Optional

import yaml

# 项目根目录（src 上一级）
PROJECT_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = PROJECT_ROOT / "config" / "sources.yaml"

_logger = logging.getLogger(__name__)


def load_config(path: Optional[Path] = None) -> dict[str, Any]:
    """加载 sources.yaml 配置；缺失时返回空 dict，不阻断启动。"""
    p = path or CONFIG_PATH
    try:
        if p.exists():
            with p.open(encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
    except Exception as exc:  # noqa: BLE001
        _logger.warning("配置加载失败 %s: %s", p, exc)
    return {}


def get_download_base(cfg: dict[str, Any]) -> Path:
    """下载根目录（env 优先 -> 配置 -> 默认 downloads）。"""
    env = os.getenv("MEE_DOWNLOAD_DIR")
    if env:
        p = Path(env)
    else:
        p = PROJECT_ROOT / (cfg.get("download", {}).get("base_dir", "downloads"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def ensure_within(base: Path, target: Path) -> Path:
    """确保目标路径位于 base 目录内（防路径穿越）。"""
    base = base.resolve()
    target = (base / target).resolve()
    if not str(target).startswith(str(base)):
        raise ValueError(f"路径越界被拒绝: {target}")
    return target


def setup_logging(level: str = "INFO", audit_file: Optional[str] = None) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    if audit_file:
        try:
            fh = logging.FileHandler(audit_file, encoding="utf-8")
            fh.setLevel(logging.INFO)
            logging.getLogger("audit").addHandler(fh)
        except Exception as exc:  # noqa: BLE001
            _logger.warning("审计日志初始化失败: %s", exc)


def audit(operation: str, detail: str) -> None:
    """写审计日志（只读操作也会留痕）。"""
    logging.getLogger("audit").info("[%s] %s", operation, detail)
