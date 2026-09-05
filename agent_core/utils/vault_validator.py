#!/usr/bin/env python3
"""
agent_core/utils/vault_validator.py — Obsidian vault 路径校验（路径遍历防护）

门禁2 的可复用实现：resolve 消解软链与 .. 后，命中系统敏感目录即拒绝；
可选 root 参数把路径进一步约束在指定子树内（白名单模式）。
"""

from __future__ import annotations

from pathlib import Path

# 系统敏感目录（resolve 后命中即拒绝；/etc 经 resolve 已覆盖 /private/etc 软链）
_FORBIDDEN_ROOTS = tuple(
    Path(p).expanduser().resolve()
    for p in ("/etc", "/proc", "/sys", "/dev", "/root", "/usr", "/bin", "/sbin", "/Library", "/System")
)


def validate_vault_path(path, root: str | Path | None = None) -> Path | None:
    """校验 vault 路径，返回安全的 resolved Path；拒绝时返回 None。

    - `path`：待校验的同步目录（可能含 ../ 或系统路径）。
    - `root`：可选允许根目录；提供时路径必须落在 root 子树内（白名单），否则拒绝。
    """
    try:
        p = Path(path).expanduser().resolve()
    except Exception:  # noqa: BLE001 — 非法路径一律拒绝
        return None
    if root is not None:
        try:
            p.relative_to(Path(root).expanduser().resolve())
        except ValueError:
            return None
    for forbidden in _FORBIDDEN_ROOTS:
        try:
            p.relative_to(forbidden)
            return None
        except ValueError:
            continue
    return p
