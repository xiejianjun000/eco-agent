"""环评云 MCP（mcp.eiacloud.com）接线测试。

4 台服务器 / 11 个工具，全部 L1 只读：
  law-keyword   法规导则关键词检索（103075 份文件）
  law-semantic  法规导则语义检索（63905 份）
  qa            官方答复与部长信箱口径（6523 份）
  emission      大气/水排放限值结构化数值库（428 份）

注意：此前白名单里的 mcp__eia__kb_search 等 4 个是历史遗留占位名，
对应服务器并不存在，提示词里的 mcp__eia__* 一直是空指向。
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

EIA_TOOLS = (
    "mcp__eia-law-keyword__search_keyword_policy",
    "mcp__eia-law-keyword__search_keyword_standard",
    "mcp__eia-law-semantic__search_nationwide_semantic_policy",
    "mcp__eia-law-semantic__search_nationwide_semantic_standard",
    "mcp__eia-law-semantic__search_semantic_province_sta_pol",
    "mcp__eia-qa__search_keyword_qa",
    "mcp__eia-qa__search_semantic_qa",
    "mcp__eia-emission__query_emission_water_place",
    "mcp__eia-emission__query_emission_water_country",
    "mcp__eia-emission__query_emission_gas_place",
    "mcp__eia-emission__query_emission_gas_country",
)


def test_all_eia_tools_whitelisted():
    """11 个工具必须全在聊天白名单里，少一个就调不到。"""
    from server.api.chat import _CHAT_MCP_TOOLS
    missing = [t for t in EIA_TOOLS if t not in _CHAT_MCP_TOOLS]
    assert not missing, f"白名单缺失: {missing}"


def test_dead_placeholder_removed():
    """历史占位名指向不存在的服务器，必须清掉，否则模型会调空。"""
    from server.api.chat import _CHAT_MCP_TOOLS
    dead = [t for t in _CHAT_MCP_TOOLS if t.startswith("mcp__eia__")]
    assert not dead, f"仍有失效占位名: {dead}"


def test_all_eia_tools_are_readonly():
    """全部是查询工具，只读模式下不能被误杀。"""
    from server.api.chat import _tool_is_readonly
    not_ro = [t for t in EIA_TOOLS if not _tool_is_readonly(t)]
    assert not not_ro, f"被误判为写工具: {not_ro}"


def _env_servers():
    """直接从仓库 .env 读，不依赖 pytest 的工作目录。"""
    import json
    import re
    txt = (REPO / ".env").read_text(encoding="utf-8")
    m = re.search(r"ECO_MCP_SERVERS='(\[.*?\])'", txt, re.S)
    assert m, ".env 里没有 ECO_MCP_SERVERS"
    return json.loads(m.group(1))


# 下面两个用例校验的是「本机环境配置」而非代码正确性，硬依赖仓库根的
# .env。而 .env 含密钥、本就不该进版本库，CI 检出后必然缺失 ——
# 这正是 CI 一直红的原因（FileNotFoundError: .../eco-agent/.env）。
# 缺 .env 时如实跳过：本地开发照常校验，CI 不再被环境问题误判成代码缺陷。
_needs_env = pytest.mark.skipif(
    not (REPO / ".env").exists(),
    reason="需要仓库根 .env（含密钥，不进版本库）；CI 环境无此文件",
)


@_needs_env
def test_servers_configured():
    """4 台服务器配置必须在 ECO_MCP_SERVERS 里。"""
    names = {c["name"] for c in _env_servers()}
    for want in ("eia-law-keyword", "eia-law-semantic", "eia-qa", "eia-emission"):
        assert want in names, f"缺少服务器配置: {want}"


def test_all_eia_tools_are_l1():
    """权限门必须判 L1，否则非交互模式直接 permission denied。

    实测教训：token 换成真的之后调用仍然失败，报的是
    「permission denied [L3]: 非交互模式拒绝（白名单外 L3）」——
    模型收到这个就会反复换工具，8 次调用还没拿到数据。
    MCP 工具默认 L3（服务端不受信，写操作可能伪装成 query_ 前缀），
    必须把服务器显式加进 _READONLY_MCP_SERVERS 才降 L1。
    """
    from agent_core.permissions import tool_risk_level
    bad = [t for t in EIA_TOOLS if tool_risk_level(t) != "L1"]
    assert not bad, f"未降到 L1，非交互模式会被拒: {bad}"


def test_dead_eia_server_removed_from_trust():
    """信任名单里的 "eia" 指向不存在的服务器，属历史遗留。"""
    from agent_core.permissions import _READONLY_MCP_SERVERS
    assert "eia" not in _READONLY_MCP_SERVERS


@_needs_env
def test_servers_use_bearer_auth():
    """环评云用 Bearer token；认证头写错会静默返回 4001/4002。"""
    for c in _env_servers():
        if c["name"].startswith("eia-"):
            auth = c.get("headers", {}).get("Authorization", "")
            assert auth.startswith("Bearer "), f"{c['name']} 认证头格式错"
            assert c["transport"] == "http", f"{c['name']} 传输应为 http"
            assert c["url"].startswith("https://mcp.eiacloud.com/")
