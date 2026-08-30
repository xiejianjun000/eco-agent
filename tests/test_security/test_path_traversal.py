#!/usr/bin/env python3
"""门禁2：路径遍历防御（对应 B2）

校验 vault 路径：resolve 消解 ../ 与软链后，命中系统敏感目录即拒绝；
`root` 参数提供白名单约束。
"""
from __future__ import annotations

from pathlib import Path

from agent_core.utils.vault_validator import validate_vault_path
from _scripts.memory_tree import MemoryTree


def test_system_paths_rejected():
    for p in ("/etc/passwd", "/etc", "/proc", "/sys", "/dev", "/usr",
              "/root", "/Library", "/System"):
        assert validate_vault_path(p) is None, f"应拒绝系统路径: {p}"


def test_traversal_rejected_with_root(tmp_path: Path):
    """带 root 白名单时，../ 逃逸被拒绝。"""
    root = tmp_path / "vault"
    assert validate_vault_path(tmp_path / "vault" / "sub", root=root) is not None
    assert validate_vault_path(tmp_path / ".." / "escape", root=root) is None
    assert validate_vault_path("/etc", root=root) is None


def test_legitimate_vault_allowed(tmp_path: Path):
    assert validate_vault_path(tmp_path / "my-vault") is not None


def test_sync_to_obsidian_blocks_system_dir(tmp_path: Path):
    """端到端：sync_to_obsidian 传系统路径 → 不写文件、返回错误。"""
    mt = MemoryTree(db_path=tmp_path / "mem.db")
    mt.create_node("case", "t", "c", tags=["env"])
    r = mt.sync_to_obsidian(vault_path=Path("/etc"))
    assert r.get("synced", 0) == 0
    assert r.get("errors"), "应返回路径遍历防护错误"
