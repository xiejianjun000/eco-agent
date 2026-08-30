#!/usr/bin/env python3
"""文档与代码一致性检查（Part 2 → 自动化）

检查1：README 入口命令真实可执行（`python3 -m eco.cli server --help` 退出码 0）
检查2：自定义异常在文档中有说明（README + docs/）
检查3：无 API key 时友好降级（非 KeyError 堆栈）
"""
from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent.parent


# ── 检查1：README 入口命令 ──────────────────────────────

def test_cli_entry_help_exits_zero():
    """真实入口 `python3 -m eco.cli server --help` 必须可执行（退出码 0）。"""
    r = subprocess.run(
        [sys.executable, "-m", "eco.cli", "server", "--help"],
        capture_output=True, text=True, timeout=60, cwd=ROOT)
    assert r.returncode == 0, f"eco.cli server --help 失败: {r.stderr[:300]}"


def test_readme_mentions_cli_entry():
    """README 快速开始应提及主入口（而非只写已废弃的 gateway/daemon.py）。"""
    readme = (ROOT / "README.md").read_text(encoding="utf-8", errors="ignore")
    assert "eco.cli" in readme or "eco server" in readme, \
        "README 未提及主入口 `eco.cli server`"


# ── 检查2：自定义异常文档覆盖 ──────────────────────────

def _custom_exceptions() -> list[str]:
    names = []
    for py in ROOT.glob("agent_core/**/*.py"):
        try:
            tree = ast.parse(py.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and \
               any(b.id in ("Exception", "RuntimeError", "ValueError", "OSError")
                   for b in node.bases if isinstance(b, ast.Name)):
                names.append(node.name)
    return sorted(set(names))


def test_exceptions_documented():
    """每个自定义异常必须在 README 或 docs/ 中被提及。"""
    docs = (ROOT / "README.md").read_text(encoding="utf-8", errors="ignore")
    for f in (ROOT / "docs").glob("*.md"):
        docs += "\n" + f.read_text(encoding="utf-8", errors="ignore")
    missing = [e for e in _custom_exceptions() if e not in docs]
    assert not missing, f"以下异常未在文档说明: {missing}"


# ── 检查3：环境变量兜底 ──────────────────────────────

def test_missing_api_key_graceful(monkeypatch):
    """删掉所有 LLM key，客户端应返回友好错误，而非 KeyError 堆栈。"""
    for k in list(os.environ):
        if "API_KEY" in k or k in ("ECO_MASTER_KEY",):
            monkeypatch.delenv(k, raising=False)
    from agent_core.llm_client import get_default_client
    client = get_default_client()
    # 调一次：应返回 (None, 错误消息) 而非抛 KeyError
    result = client.chat([{"role": "user", "content": "hi"}], model="")
    assert result is not None
    # 错误消息应为友好提示（含 api key 关键词），非 Traceback
    if isinstance(result, tuple):
        _, err = result
        assert err and ("api key" in err.lower() or "key" in err.lower()), \
            f"错误消息不友好: {err}"
