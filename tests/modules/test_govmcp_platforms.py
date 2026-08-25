"""政务平台三 MCP govmcp 格式挂载回归测试
===========================================
覆盖三个私有仓库 MCP 转换产物（govmcp_tools/{wryzxjc,sthjzf,permit_management}.py）：
1. govmcp 注册表挂载（register_all 包含三平台，schema 推断正确）
2. 逆向算法单元测试（HTML 解析 / AES 加密 / RSA / MD5 签名）
3. 敏感写入双闸门（confirm=False 短路，不发网络请求）
4. 聊天通道接线（聊天工具表包含三平台只读工具 + handler 已注册）
"""

from __future__ import annotations

import base64
import hashlib
import json

import pytest


# ── 1. govmcp 注册表挂载 ─────────────────────────────────────────

def test_register_all_mounts_three_platforms():
    from govmcp.tools.registry import ToolRegistry
    from govmcp_tools import register_all

    reg = ToolRegistry()
    register_all(reg)
    names = {t["name"] for t in reg.list_tools()}

    # 在线监测（11）
    for n in (
        "wryzxjc_login", "wryzxjc_status", "wryzxjc_list_regions",
        "wryzxjc_list_pollution_sources", "wryzxjc_get_pollution_source",
        "wryzxjc_list_alarms", "wryzxjc_list_devices",
        "wryzxjc_list_realtime_data", "wryzxjc_list_jcd_tree",
        "wryzxjc_list_history_data", "wryzxjc_raw_query",
    ):
        assert n in names, f"在线监测工具缺失: {n}"
    # 国家四平台（17）
    for n in (
        "sthjzf_login", "sthjzf_status", "sthjzf_list_views", "sthjzf_query_view",
        "sthjzf_get_menu", "sthjzf_get_view_config", "sthjzf_query_cases",
        "sthjzf_list_depts", "sthjzf_query_case_detail", "sthjzf_query_case_statistics",
        "sthjzf_water_current_user", "sthjzf_water_task_statistics",
        "sthjzf_water_task_list", "sthjzf_water_supervise_statistics",
        "sthjzf_water_clue_verify", "sthjzf_water_clue_confirm", "sthjzf_water_api",
    ):
        assert n in names, f"国家四平台工具缺失: {n}"
    # 排污许可（11）
    for n in (
        "permit_login", "permit_status", "permit_menu", "permit_license_list",
        "permit_enterprise_list", "permit_jgzf_menu", "permit_jgzf_license_execution",
        "permit_jgzf_stop_production", "permit_jgzf_enterprise_archive",
        "permit_area_list", "permit_industry_list",
    ):
        assert n in names, f"排污许可工具缺失: {n}"


def test_write_tools_flagged_approval_required():
    from govmcp.tools.registry import ToolRegistry
    from govmcp_tools import register_all

    reg = ToolRegistry()
    register_all(reg)
    assert reg.get("sthjzf_water_clue_verify").approval_required is True
    assert reg.get("sthjzf_water_clue_confirm").approval_required is True
    # 只读工具不要求审批
    assert reg.get("sthjzf_water_task_list").approval_required is False


def test_input_schema_inference():
    from govmcp.tools.registry import ToolRegistry
    from govmcp_tools import register_all

    reg = ToolRegistry()
    register_all(reg)
    schema = reg.get("wryzxjc_list_history_data").input_schema
    assert schema["type"] == "object"
    for prop in ("jcdxh", "jcdlx", "sjlx", "quick", "start_time", "end_time"):
        assert prop in schema["properties"]


# ── 2. 在线监测：HTML 解析 ─────────────────────────────────────────

def test_wryzxjc_parse_rows_skips_action_columns():
    from govmcp_tools.wryzxjc import _parse_rows

    html = """
    <table>
    <tr id="trid1" XH=1001>
      <td>冷水江某化工厂</td><td>冷水江市</td>
      <td><i class="icon-eye"></i>查看</td><td>导出</td>
    </tr>
    <tr id="trid2" XH=1002>
      <td>某钢铁厂</td><td>涟源市</td><td>详细情况</td>
    </tr>
    </table>
    """
    rows = _parse_rows(html)
    assert len(rows) == 2
    assert rows[0]["xh"] == "1001"
    assert rows[0]["cells"] == ["冷水江某化工厂", "冷水江市"]
    assert rows[1]["xh"] == "1002"
    assert rows[1]["cells"] == ["某钢铁厂", "涟源市"]


def test_wryzxjc_parse_rows_preserves_empty_cells():
    from govmcp_tools.wryzxjc import _parse_rows

    html = '<tr id="trid1" XH=9><td></td><td>pH</td><td>7.2</td></tr>'
    rows = _parse_rows(html)
    assert rows[0]["cells"] == ["", "pH", "7.2"]


def test_wryzxjc_get_total():
    from govmcp_tools.wryzxjc import _get_total

    assert _get_total('<input type="hidden" name="P_RECORD_COUNT" value="137">') == 137
    assert _get_total("<html>无数据</html>") == 0


# ── 3. 国家四平台：AES 加密与写入双闸门 ───────────────────────────

def test_sthjzf_encrypt_password():
    from govmcp_tools.sthjzf import _encrypt_password
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import pad

    expected = base64.b64encode(
        AES.new(b"boandaxxjsgfyxgs", AES.MODE_ECB).encrypt(pad(b"test1234", 16))
    ).decode()
    assert _encrypt_password("test1234") == expected


def test_sthjzf_water_clue_verify_confirm_gate():
    """写入工具 confirm=False 时短路返回 blocked，不发任何网络请求。"""
    from govmcp_tools.sthjzf import sthjzf_water_clue_verify

    result = sthjzf_water_clue_verify(
        clue_id="abc", task_type="A", is_true=1, situation="x", confirm=False
    )
    assert result.get("blocked") is True


def test_sthjzf_water_clue_confirm_gate():
    from govmcp_tools.sthjzf import sthjzf_water_clue_confirm

    result = sthjzf_water_clue_confirm(task_id="abc", is_pass=1, confirm=False)
    assert result.get("blocked") is True


def test_sthjzf_water_task_list_rejects_invalid_type():
    """非法线索类型在未登录前就返回参数错误（不发网络请求）。"""
    from govmcp_tools.sthjzf import sthjzf_water_task_list

    result = sthjzf_water_task_list(task_type="Z")
    assert result["success"] is False
    assert "A-J" in result["error"]


def test_sthjzf_login_missing_credentials():
    import govmcp_tools.sthjzf as m

    saved_u = m.os.environ.pop("STHJZF_USERNAME", None)
    saved_p = m.os.environ.pop("STHJZF_PASSWORD", None)
    try:
        result = m.sthjzf_login()
        assert result["success"] is False
        assert "STHJZF_USERNAME" in result["message"]
    finally:
        if saved_u is not None:
            m.os.environ["STHJZF_USERNAME"] = saved_u
        if saved_p is not None:
            m.os.environ["STHJZF_PASSWORD"] = saved_p


# ── 4. 排污许可：RSA / modulus / MD5 签名 ─────────────────────────

def test_permit_rsa_encrypt_matches_raw_pow():
    from govmcp_tools.permit_management import rsa_encrypt, E, CHUNK

    modulus = "e5d1f0" + "0" * 30  # 任意模数
    pwd = "Abc123"
    data = pwd.encode("utf-8")
    a = list(data) + [0] * (CHUNK - len(data))
    block_int = int.from_bytes(bytes(a), "little")
    expected = hex(pow(block_int, E, int(modulus, 16)))[2:]
    assert rsa_encrypt(pwd, modulus) == expected


def test_permit_extract_modulus():
    from govmcp_tools.permit_management import extract_modulus

    mod = "a1b2c3d4" * 32
    html = f'<script>getKeyPair("10001","","{mod}")</script>'
    assert extract_modulus(html) == mod


def test_permit_extract_error():
    from govmcp_tools.permit_management import extract_error

    html = '<font color="#FF0000">用户名或密码错误</font>'
    assert extract_error(html) == "用户名或密码错误"


def test_permit_jgzf_sign_md5_vector():
    from govmcp_tools.permit_management import jgzf_sign
    import govmcp_tools.permit_management as m

    saved_key = m.JGZF_KEY
    m.JGZF_KEY = "secretkey"
    try:
        headers = jgzf_sign("tok", '{"a":1}')
        # 用固定 timestamp 复算：调用返回的 timestamp 参与 MD5
        raw = "1.0" + headers["timestamp"] + "tok" + '{"a":1}' + "secretkey"
        assert headers["sign"] == hashlib.md5(raw.encode()).hexdigest()
        assert headers["version"] == "1.0"
    finally:
        m.JGZF_KEY = saved_key


def test_permit_not_configured_returns_guidance():
    """未配置内网环境变量时返回配置指引而非异常。"""
    import govmcp_tools.permit_management as m

    saved_base = m.BASE
    saved_un = m.os.environ.pop("PERMIT_USERNAME", None)
    saved_pw = m.os.environ.pop("PERMIT_PASSWORD", None)
    m.BASE = ""
    try:
        result = m.permit_license_list()
        assert result["success"] is False
        assert "PERMIT_BASE" in result["error"]
    finally:
        m.BASE = saved_base
        if saved_un is not None:
            m.os.environ["PERMIT_USERNAME"] = saved_un
        if saved_pw is not None:
            m.os.environ["PERMIT_PASSWORD"] = saved_pw


# ── 5. 聊天通道接线 ──────────────────────────────────────────────

def test_chat_tool_list_includes_platform_tools():
    from agent_core.wiring_manifest import WIRED_REQUIRED
    from server.api.chat import _codex_tools

    wired = {t["function"]["name"] for t in _codex_tools()}
    platform = [n for n in WIRED_REQUIRED
                if n.startswith(("wryzxjc_", "sthjzf_", "permit_"))]
    assert len(platform) >= 28, "接线清单平台工具数量异常"
    missing = [n for n in platform if n not in wired]
    assert not missing, f"三平台聊天工具未接入: {missing}"


def test_chat_platform_handlers_registered():
    """聊天清单里的三平台工具必须能反查到真实 handler（防'注册了但没接线'）。"""
    from agent_core.tools_registry import _HANDLERS, resolve_tool_name
    from server.api.chat import _PLATFORM_CHAT_NAMES, _ensure_platform_tools

    _ensure_platform_tools()
    assert len(_PLATFORM_CHAT_NAMES) == 31  # 28 政务平台 + 2 环境公开数据源 + 1 湖南月报
    no_handler = [
        n for n in _PLATFORM_CHAT_NAMES
        if n not in _HANDLERS and resolve_tool_name(n) not in _HANDLERS
    ]
    assert not no_handler, f"三平台聊天工具没有 handler: {no_handler}"


def test_write_tools_not_in_chat_list():
    """敏感写入工具不进聊天工具表（凭证/写入不暴露给模型直接调用）。"""
    from server.api.chat import _PLATFORM_CHAT_NAMES, _ensure_platform_tools

    _ensure_platform_tools()
    assert "sthjzf_water_clue_verify" not in _PLATFORM_CHAT_NAMES
    assert "sthjzf_water_clue_confirm" not in _PLATFORM_CHAT_NAMES
    assert "wryzxjc_login" not in _PLATFORM_CHAT_NAMES
    assert "permit_login" not in _PLATFORM_CHAT_NAMES
    assert "wryzxjc_raw_query" not in _PLATFORM_CHAT_NAMES
    assert "sthjzf_water_api" not in _PLATFORM_CHAT_NAMES
