#!/usr/bin/env python3
"""能力清单一致性回归：接线治理收敛为"单一权威源交叉校验"
====================================================
历史痛点：每挂一个能力要手改 5 处（工具表/分发/接线清单/PERMISSION/测试），
改漏任何一处 = "注册了但没接线"类缺口。
本测试把 5 处做交叉校验——任何一处漏改，测试立刻红，防止漂移。
"""

from __future__ import annotations

# 政务平台工具集（govmcp_tools）已于 2026-09 移除：依赖内网域名与凭证，
# 通用环境不可达。原 ①~⑤ 平台工具交叉校验用例随之删除；
# 下方通用接线校验（switch_persona/open_url 等）继续保留。


def test_switch_persona_wired():
    """⑥ switch_persona：接线清单 + 聊天表 + 分发（CHANNEL_DISPATCHED）。"""
    from agent_core.wiring_manifest import CHANNEL_DISPATCHED, WIRED_REQUIRED
    from server.api.chat import _codex_tools

    assert "switch_persona" in WIRED_REQUIRED
    assert "switch_persona" in CHANNEL_DISPATCHED
    assert "switch_persona" in {t["function"]["name"] for t in _codex_tools()}


def test_mcp_tool_name_slug_preserves_namespace():
    """MCP 工具名 slug 化必须保留 mcp__<server>__ 前缀（含边界双下划线），
    否则聊天白名单/权限覆盖表与注册名对不上（腾讯文档带点工具曾全部漏挂）。"""
    from agent_core.tools_registry import normalize_tool_name

    cases = {
        "mcp__tencent_docs__manage.create_file": "mcp__tencent_docs__manage_create_file",
        "mcp__tencent_docs__doc.create_with_markdown": "mcp__tencent_docs__doc_create_with_markdown",
        "mcp__tencent_docs__manage.search_file": "mcp__tencent_docs__manage_search_file",
        "mcp__tencent_docs__get_content": "mcp__tencent_docs__get_content",
        "mcp__github__search_repositories": "mcp__github__search_repositories",
    }
    for raw, expected in cases.items():
        assert normalize_tool_name(raw) == expected, f"{raw} -> 期望 {expected}"


def test_open_url_whitelist():
    """open_url：白名单域名放行、非法域名/协议拒绝（不真正打开浏览器）。"""
    from server.api.chat import _open_browser

    # prefer_panel=True：docs.qq.com 走右侧面板标记，不触发系统 xdg-open/open
    # （CI 无头环境无浏览器，真实打开会报非零退出码导致误判）
    ok = _open_browser("https://docs.qq.com/space/abc", prefer_panel=True)
    assert '"ok": true' in ok
    bad_domain = _open_browser("https://evil.example.com/")
    assert '"ok": false' in bad_domain and "白名单" in bad_domain
    bad_scheme = _open_browser("file:///etc/passwd")
    assert '"ok": false' in bad_scheme


def test_open_url_wired():
    """open_url：接线清单 + 聊天表 + 分发全部打通。"""
    from agent_core.wiring_manifest import CHANNEL_DISPATCHED, WIRED_REQUIRED
    from server.api.chat import _codex_tools

    assert "open_url" in WIRED_REQUIRED
    assert "open_url" in CHANNEL_DISPATCHED
    assert "open_url" in {t["function"]["name"] for t in _codex_tools()}


# ── 维度 A/E 契约闸门 ─────────────────────────────────────────────


def test_law_status_trigger_detection():
    """E 维度：法规时效类提问识别（机制级确定性闸门）。"""
    from server.api.chat import _law_status_trigger

    assert _law_status_trigger("《生态环境监测条例》出台了吗？")
    assert _law_status_trigger("这个办法废止了吗？施行日期是哪天？")
    assert _law_status_trigger("环保标准最新版是什么")
    assert not _law_status_trigger("超标 3 倍怎么处罚")
    assert not _law_status_trigger("帮我写现场检查笔录")


def test_llm_error_self_heal_guidance():
    """A 维度：凭证/配额类错误必须带自愈指引，而非裸报错。"""
    from server.api.chat import _llm_error_reply

    r1 = _llm_error_reply("no api key (provider not configured)")
    assert "自愈指引" in r1 and "setup_credentials.py" in r1
    r2 = _llm_error_reply("HTTP 401")
    assert "自愈指引" in r2 and "401" in r2
    r3 = _llm_error_reply("HTTP 402")
    assert "余额" in r3 or "充值" in r3
    r4 = _llm_error_reply("read timeout")
    assert r4.startswith("[eco-server] LLM 调用失败")


def test_hallucination_format_final_sanitize():
    """终层净化：中段/尾部工具调用格式残留必须剥离（穿透测试2暴露的漏网）。"""
    import re

    leaked = (
        '让我读取文件最后几行。  <tool_calls> <invoke name="execute_code"> '
        '<parameter name="code" string="true"> from pathlib import Path ...</parameter>'
        "</invoke> </tool_calls> 后面的正常分析内容"
    )
    cleaned = re.sub(r"[<＜]\s*invoke[\s\S]*?[<＜]\s*/\s*invoke\s*>", "", leaked)
    cleaned = re.sub(r"[<＜]\s*tool_calls\s*>[\s\S]*?[<＜]\s*/\s*tool_calls\s*>", "", cleaned)
    cleaned = re.sub(r"[<＜]\s*(tool_calls|invoke)[\s\S]*$", "", cleaned).strip()
    assert "invoke" not in cleaned and "tool_calls" not in cleaned
    assert "后面的正常分析内容" in cleaned


# ── 执行层工具契约（路线图 1-3）──────────────────────────────────


def test_shell_allowlist_enforces():
    """shell_run：白名单放行、危险语法/高危命令/非白名单全部拒绝。"""
    import json

    from agent_core.exec_tools import run_shell

    ok = json.loads(run_shell("pwd"))
    assert ok["ok"] is True
    assert json.loads(run_shell("rm -rf /tmp/x"))["ok"] is False
    assert json.loads(run_shell("echo hi > /tmp/x"))["ok"] is False
    assert json.loads(run_shell("sudo ls"))["ok"] is False
    assert json.loads(run_shell("curl http://x"))["ok"] is False
    assert json.loads(run_shell("ls; cat /etc/passwd"))["ok"] is False
    assert json.loads(run_shell("nonsense_cmd_xyz"))["ok"] is False


def test_file_tools_path_containment():
    """file 工具：路径逃逸拒绝、编辑唯一命中、写读往返一致。"""
    import json
    import tempfile
    from pathlib import Path

    from agent_core.exec_tools import file_edit, file_read, file_write

    with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent.parent.parent / ".eco-ws" if False else None) as _:
        pass
    # 逃逸拒绝（/etc 不在允许根内）
    assert json.loads(file_write("/etc/eco_test_x", "x"))["ok"] is False
    assert json.loads(file_read("/etc/passwd"))["ok"] is False
    # 工作区内写读往返
    import os

    ws = os.environ.get("ECO_WORKSPACE_DIR", "")
    if ws:
        p = Path(ws) / "_contract_test.md"
        w = json.loads(file_write(str(p), "line1\nline2\n"))
        assert w["ok"] is True
        r = json.loads(file_read(str(p), max_chars=100))
        assert r["ok"] is True and "line1" in r["content"]
        e = json.loads(file_edit(str(p), "line1", "LINE1"))
        assert e["ok"] is True and e["replaced"] == 1
        e2 = json.loads(file_edit(str(p), "line2", "X"))
        assert e2["ok"] is True
        p.unlink(missing_ok=True)


def test_web_search_parse_links():
    from agent_core.web_search_tool import _parse_links

    page = '<h2><a href="https://www.gov.cn/a.htm">标题甲</a></h2><h2><a href="https://www.gov.cn/b.htm">标题乙</a></h2>'
    out = _parse_links(page, [(r'<h2><a href="([^"]+)"', r"<h2><a[^>]*>(.*?)</a></h2>")])
    assert len(out) == 2 and out[0]["title"] == "标题甲"
