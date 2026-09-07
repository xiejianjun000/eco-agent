#!/usr/bin/env python3
"""穿透取证工具测试：grep/glob/api_probe/file_read 分页 + 系统状态结论 gate。

覆盖三层能力补全：
  L1 感知 — inspect 已注入 agent 工具集（工具定义存在）
  L2 穿透 — grep/glob 可定位源码，file_read 可按行分页
  L3 验证 — api_probe 只读边界 + _sys_claim_trigger 结论 gate 精度
"""

import json

import pytest

# ─── L2：穿透工具 ────────────────────────────────────────────────


def test_grep_finds_symbol_with_line_number():
    from agent_core.exec_tools import code_grep

    r = json.loads(code_grep(r"^def code_grep", include="*.py"))
    assert r["ok"] is True
    assert r["match_count"] >= 1
    # 定义处只应出现在实现文件中
    assert any(m["file"].endswith("exec_tools.py") for m in r["matches"])
    hit = r["matches"][0]
    assert isinstance(hit["line"], int) and hit["line"] > 0


def test_grep_rejects_invalid_regex():
    from agent_core.exec_tools import code_grep

    r = json.loads(code_grep("([unclosed"))
    assert r["ok"] is False
    assert "正则" in r["error"]


def test_glob_discovers_files_by_basename():
    from agent_core.exec_tools import code_glob

    r = json.loads(code_glob("exec_tools.py"))
    assert r["ok"] is True
    assert r["count"] >= 1
    assert any(f.endswith("exec_tools.py") for f in r["files"])


def test_glob_skips_noise_dirs():
    from agent_core.exec_tools import code_glob

    r = json.loads(code_glob("*.pyc"))
    assert r["ok"] is True
    assert not any("__pycache__" in f for f in r["files"])


def test_file_read_paged_returns_line_numbers(tmp_path):
    # 用仓库内文件（受可读根限制）
    from pathlib import Path

    from agent_core.exec_tools import file_read

    target = Path(__file__).resolve()
    r = json.loads(file_read(str(target), offset=1, limit=3))
    assert r["ok"] is True
    assert r["start_line"] == 1
    assert r["returned_lines"] == 3
    assert r["has_more"] is True
    assert r["next_offset"] == 4
    # 内容带行号前缀
    assert r["content"].lstrip().startswith("1:")


def test_file_read_compat_mode_unchanged():
    """不传 offset/limit 时保持旧行为（整文件 + chars 字段）。"""
    from pathlib import Path

    from agent_core.exec_tools import file_read

    r = json.loads(file_read(str(Path(__file__).resolve())))
    assert r["ok"] is True
    assert "chars" in r
    assert "start_line" not in r


# ─── L3：api_probe 只读边界 ──────────────────────────────────────


@pytest.mark.parametrize("url", ["https://example.com/x", "http://8.8.8.8/y"])
def test_api_probe_rejects_non_loopback(url):
    from agent_core.exec_tools import api_probe

    r = json.loads(api_probe(url))
    assert r["ok"] is False
    assert "环回" in r["error"]


def test_api_probe_rejects_write_methods():
    from agent_core.exec_tools import api_probe

    r = json.loads(api_probe("/api/health", method="POST"))
    assert r["ok"] is False
    assert "只允许" in r["error"]


def test_curl_still_forbidden_in_shell():
    """api_probe 是窄通道；shell 的 curl 仍应保持封禁。"""
    from agent_core.exec_tools import SHELL_ALLOWED, run_shell

    assert "curl" not in SHELL_ALLOWED
    r = json.loads(run_shell("curl http://127.0.0.1/"))
    assert r["ok"] is False


# ─── L3：系统状态结论 gate 精度 ─────────────────────────────────


@pytest.mark.parametrize("text", [
    "经查，当前系统 0 个 MCP 没有挂载，mcp_count 返回 0。",
    "这 5 个 MCP 服务均未挂载到当前进程。",
    "inspect 模块未注册为 agent 工具，因此不可用。",
    "缺少 grep 工具，无法定位源码。",
])
def test_sys_claim_trigger_fires_on_unevidenced_state_claims(text):
    from server.api.chat import _sys_claim_trigger

    assert _sys_claim_trigger(text) is True


@pytest.mark.parametrize("text", [
    "该企业未取得排污许可证，属于无证排污。",
    "现场检查发现污水处理设施未正常运行，废水直排。",
    "根据《水污染防治法》第八十三条，应处二十万元以上罚款。",
    "监测数据显示 COD 浓度为 0 mg/L，设备可能未校准。",
    "好的，我来帮你看看。",
])
def test_sys_claim_trigger_ignores_business_conclusions(text):
    """执法业务结论不得被误判为系统状态断言（防 gate 误伤主业）。"""
    from server.api.chat import _sys_claim_trigger

    assert _sys_claim_trigger(text) is False


# ─── L1：自省工具已注入 ─────────────────────────────────────────


def test_inspect_and_probe_tools_registered_in_toolset():
    from server.api.chat import _codex_tools

    names = {t["function"]["name"] for t in _codex_tools()}
    for expected in ("inspect", "grep", "glob", "api_probe"):
        assert expected in names, f"{expected} 未注入 agent 工具集"


def test_evidence_tools_cover_probe_paths():
    from server.api.chat import _EVIDENCE_TOOLS

    for t in ("api_probe", "inspect", "grep", "file_read", "shell_run"):
        assert t in _EVIDENCE_TOOLS
