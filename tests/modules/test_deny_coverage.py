#!/usr/bin/env python3
"""tests/modules/test_deny_coverage.py — deny 层覆盖面回归

背景（真实缺陷，非假想）：
  gate_tool_call 的 deny 检查原先只读固定四个参数键
  （command / code / path / filename），于是同一个危险路径
  换一个参数名就能绕过整个 deny 层：

      gate_tool_call("file_read", {"path": "/etc/shadow"})       → 拒绝 ✅
      gate_tool_call("file_read", {"file_path": "/etc/shadow"})  → 放行 ❌

  而仓内确有以 file_path 命名的工具（analyze_document）。

本文件锁死两件事：
  1. 常见路径/命令参数别名一律进入 deny 检查；
  2. PERMISSION.md 声明的 deny 块（**/.env、*.key、*.pem）真实生效。

deny 是安全底座，只能加严不能放宽 —— 这些用例失败即视为回归。
"""

from __future__ import annotations

import pytest

from agent_core.permissions import gate_tool_call

# ── 路径参数别名：同一危险路径，换键名必须同样被拒 ────────────────
PATH_KEYS = ["path", "filename", "file_path", "filepath", "target", "dest",
             "destination", "src", "source", "output_path", "input_path", "dir"]


@pytest.mark.parametrize("key", PATH_KEYS)
def test_shadow_denied_under_every_path_alias(key):
    """/etc/shadow 在任何路径参数别名下都必须被拒绝。"""
    ok, _level, why = gate_tool_call("file_read", {key: "/etc/shadow"})
    assert ok is False, f"参数名 {key} 绕过了 deny 层"
    assert "危险路径" in why


@pytest.mark.parametrize("key", PATH_KEYS)
def test_ssh_key_denied_under_every_path_alias(key):
    """~/.ssh/ 私钥同理。"""
    ok, _level, why = gate_tool_call("file_read", {key: "~/.ssh/id_rsa"})
    assert ok is False, f"参数名 {key} 绕过了 deny 层"
    assert "危险路径" in why


# ── 多键共存：任一键命中即拒（原实现只看第一个非空值）──────────────
def test_deny_hits_when_dangerous_value_is_not_first_key():
    """安全参数在前、危险参数在后时，仍须命中。

    原实现用 `get("path") or get("filename")` 短路取值，
    第一个键非空就不再看后面 —— 危险值藏在后面的键里即逃逸。
    """
    ok, _level, why = gate_tool_call(
        "file_read", {"path": "/tmp/safe.txt", "file_path": "/etc/shadow"})
    assert ok is False, "危险值不在首个键时逃过了检查"
    assert "危险路径" in why


def test_deny_hits_when_dangerous_command_is_in_cmd_alias():
    """命令别名（cmd/script/shell）同样进入危险命令检查。"""
    for key in ("command", "code", "cmd", "script", "shell"):
        ok, _level, why = gate_tool_call("shell_run", {key: "rm -rf /"})
        assert ok is False, f"命令参数名 {key} 绕过了 deny 层"
        assert "危险命令" in why


# ── PERMISSION.md deny 块：文档声明必须真实生效 ──────────────────
@pytest.mark.parametrize("path", [
    "/Users/mac/.eco/.env",
    "./.env",
    "/tmp/project/.env",
    "/tmp/secrets/private.key",
    "/tmp/certs/server.pem",
])
def test_permission_md_deny_block_is_enforced(path):
    """PERMISSION.md 声明的 **/.env、*.key、*.pem 必须真被拦。

    这些规则曾只存在于 PERMISSION.md 文本里，没有任何 loader 读取，
    属于「文档说有、代码没实现」。
    """
    ok, _level, why = gate_tool_call("file_read", {"path": path})
    assert ok is False, f"PERMISSION.md 声明的 deny 规则未生效: {path}"
    assert "危险路径" in why


# ── 不可过度拦截：正常业务路径必须照常放行 ────────────────────────
@pytest.mark.parametrize("path", [
    "/tmp/report.md",
    "./output/案卷.pdf",
    "/Users/mac/Documents/deepseek/eco-agent/README.md",
    "/tmp/env_sample.txt",      # 含 env 字样但不是 .env
    "/tmp/keynote.md",          # 含 key 字样但不是 *.key
])
def test_ordinary_paths_still_allowed(path):
    """加严 deny 不能误伤正常读取，否则等于把工具废掉。"""
    ok, _level, _why = gate_tool_call("file_read", {"path": path})
    assert ok is True, f"正常路径被误拦: {path}"


def test_hardcoded_denies_survive_md_parse_failure(monkeypatch):
    """PERMISSION.md 解析失败时，硬编码 deny 底座仍须生效。

    MD 解析是增量能力，不能成为安全底座的单点依赖。
    """
    import agent_core.permissions as P

    monkeypatch.setattr(P, "_load_md_path_denies", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    ok, _level, why = gate_tool_call("file_read", {"path": "/etc/shadow"})
    assert ok is False
    assert "危险路径" in why
