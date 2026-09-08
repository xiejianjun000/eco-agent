"""eco 运行时目录的单一权威来源。

## 为什么需要这个模块

`~/.eco` 曾被 28 个文件、33 处硬编码。任一处在受限环境下写不进去，
对应功能就静默降级——实测同时踩中三处：

    [permissions] 审计写入失败: [Errno 1] ... /Users/mac/.eco/prompt_audit.jsonl
    web checkpoint failed: [Errno 1] ... /Users/mac/.eco/checkpoints/warm1
    span tree 落盘失败（/Users/mac/.eco/traces）: [Errno 1] ...

权限审计链整条失效却只在 stderr 打一行——合规系统不能这么丢证据。
根因是进程沙箱只允许写仓库目录，而工作区根在 `~/.eco`。

## 解析顺序

1. `ECO_DIR` / `ECO_HOME` 环境变量（显式指定优先）
2. `~/.eco`（可写才用——真实探测，不看权限位）
3. `<repo>/.eco`（回退，保证审计链一定落盘）

权限位正常不代表可写：macOS TCC 与各类沙箱都会让 `drwxr-xr-x` 的
自有目录写入抛 `[Errno 1] Operation not permitted`。所以必须实写探测。
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

__all__ = ["eco_dir", "eco_subdir", "is_fallback"]

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _writable(p: Path) -> bool:
    """真实写入探测。os.access 在沙箱下会说谎，必须实写。"""
    try:
        p.mkdir(parents=True, exist_ok=True)
        probe = p / ".write-probe"
        probe.write_text("", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


@lru_cache(maxsize=1)
def eco_dir() -> Path:
    """eco 运行时根目录（进程内只解析一次）。"""
    for var in ("ECO_DIR", "ECO_HOME"):
        v = os.environ.get(var)
        if v:
            p = Path(v).expanduser()
            p.mkdir(parents=True, exist_ok=True)
            return p

    home = Path.home() / ".eco"
    if _writable(home):
        return home

    fallback = _REPO_ROOT / ".eco"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def is_fallback() -> bool:
    """当前是否处于回退目录（供启动日志与自检提示）。"""
    return eco_dir() == _REPO_ROOT / ".eco"


def eco_subdir(name: str) -> Path:
    """取子目录并确保存在，如 eco_subdir("traces")。"""
    d = eco_dir() / name
    d.mkdir(parents=True, exist_ok=True)
    return d
