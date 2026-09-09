#!/usr/bin/env python3
"""tests/modules/test_mcp_name_truth.py — MCP 工具名必须与实连一致

背景（② 与 ③ 的共同根因，运行时坐实）：

  提示词把 **不存在的服务器名** 当作「MCP 路由铁律」写给模型：
      chat.py:336  「排污许可查公开端 mcp__eco-pollution-permit__（免登录）」
      chat.py:481  「排污许可证公开信息…：mcp__eco-pollution-permit__*」
  而实连服务器叫 eco-pollution-permit-remote。模型照铁律调用 →
  工具不存在 → 换名重试 → 直到撞满 max_rounds=8。

  实测对照（487 个实连工具 vs 223 条允许清单）：
      幽灵（清单有、实际无）144 条，多是同一服务器的旧名：
          eco-gis-amap(44)          → 实为 eco-gis-amap-remote(70)
          eco-pollution-permit(12)  → 实为 eco-pollution-permit-remote(12)
          eco-permit-enterprise(23) / eco-cepc(13) / eco-sthjzf(13) …
      未列入（实际有、清单无）408 个。

  _mcp_tool_defs() 里的 `if n in by_name` 会把幽灵挡在函数清单外，
  所以幽灵不会真的可调 —— 危害全部来自**提示词里的名字**：
  模型被告知该用某个名字，实际却调不到，只能反复试错。

本文件锁死：提示词中出现的 mcp__ 服务器名必须真实存在。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
CHAT = ROOT / "server" / "api" / "chat.py"

# 已知的改名对照：左边是历史旧名（提示词里的幽灵），右边是当前实连名。
# 记在测试里而不是只改代码，是为了让下一个人看到「为什么不能写左边」。
RENAMED = {
    "eco-pollution-permit": "eco-pollution-permit-remote",
    "eco-gis-amap": "eco-gis-amap-remote",
}


def _configured_server_names() -> set[str]:
    """从 .env 的 ECO_MCP_SERVERS 取真实配置的服务器名。"""
    import json

    env = ROOT / ".env"
    if not env.is_file():
        pytest.skip("需要仓库根 .env（含密钥，不进版本库）")
    m = re.search(r"ECO_MCP_SERVERS='(\[.*?\])'", env.read_text(encoding="utf-8"), re.S)
    if not m:
        pytest.skip(".env 里没有 ECO_MCP_SERVERS")
    return {c["name"] for c in json.loads(m.group(1))}


def _prompt_server_names() -> set[str]:
    """提示词正文里出现的 mcp__<server>__ 服务器名。

    只看字符串字面量中的名字，_CHAT_MCP_TOOLS 允许清单单独由
    test_ghost_tools_not_in_allowlist 覆盖。
    """
    src = CHAT.read_text(encoding="utf-8")
    # 允许清单区间不算「提示词」
    start = src.index("_CHAT_MCP_TOOLS = (")
    end = src.index("\n)", start)
    prompt_src = src[:start] + src[end:]

    # 权限判级用的 startswith 元组是内部逻辑，不是给模型看的路由指引
    prompt_src = re.sub(r'if name\.startswith\(\([^)]*\)\):', '', prompt_src, flags=re.S)

    names = set()
    for line in prompt_src.split("\n"):
        found = re.findall(r"mcp__([a-z0-9_\-]+?)__", line)
        if not found:
            continue
        # 明确说明「未挂载/不可用/不要调」的否定句不算推荐使用 ——
        # 那正是我们希望提示词具备的诚实表述，不该被判为幽灵引用。
        if any(neg in line for neg in ("未挂载", "不可用", "不要凭印象", "不存在", "未连通")):
            continue
        names.update(found)
    return names


def test_prompt_mentions_no_renamed_server():
    """提示词不得再出现已改名的旧服务器名。"""
    mentioned = _prompt_server_names()
    stale = sorted(mentioned & set(RENAMED))
    assert not stale, (
        "提示词仍在用已改名的服务器名："
        + "；".join(f"{s} 应为 {RENAMED[s]}" for s in stale))


def test_prompt_server_names_are_all_configured():
    """提示词里每个 mcp__ 服务器名都必须在 ECO_MCP_SERVERS 里。"""
    configured = _configured_server_names()
    mentioned = _prompt_server_names()
    # tencent_docs 等下划线名在配置里可能写作连字符，两种形态都接受
    unknown = sorted(
        n for n in mentioned
        if n not in configured
        and n.replace("_", "-") not in configured
        and n.replace("-", "_") not in configured
    )
    assert not unknown, f"提示词提到未配置的 MCP 服务器: {unknown}"


def test_allowlist_has_no_renamed_server():
    """_CHAT_MCP_TOOLS 允许清单里不得残留已改名的旧服务器。

    清单里的幽灵虽然被 `if n in by_name` 挡住不会真的可调，
    但留着会误导下一个改代码的人，也让「清单」失去参考价值。
    """
    src = CHAT.read_text(encoding="utf-8")
    m = re.search(r"_CHAT_MCP_TOOLS\s*=\s*\((.*?)\n\)", src, re.S)
    assert m, "未找到 _CHAT_MCP_TOOLS"
    listed = set(re.findall(r'"mcp__([a-z0-9_\-]+?)__', m.group(1)))
    stale = sorted(listed & set(RENAMED))
    assert not stale, (
        "允许清单仍含已改名服务器："
        + "；".join(f"{s} 应为 {RENAMED[s]}" for s in stale))


def test_permit_tools_use_real_prefix():
    """排污许可工具必须用实连前缀与真实工具名。

    真实工具是 permit_pub_* 系列，挂在 eco-pollution-permit-remote 上。
    """
    src = CHAT.read_text(encoding="utf-8")
    assert "mcp__eco-pollution-permit-remote__permit_pub_" in src, (
        "允许清单/提示词里没有任何真实的排污许可公开端工具")


def test_every_allowlist_entry_exists_on_a_configured_server():
    """清单里每一条 mcp__<server>__<tool> 的 server 必须在 ECO_MCP_SERVERS 里。

    防腐化守卫：清单曾腐化到 223 条里 144 条是幽灵（65%），其中
    eco-gis-amap(44) / eco-permit-enterprise(23) / eco-cepc(13) 等
    七台服务器根本没配置，另有两台只是改了名。
    工具级存在性无法离线校验（要连服务器），但服务器级可以，
    这道门槛足以拦住「整台服务器都不存在」这类腐化。
    """
    configured = _configured_server_names()
    src = CHAT.read_text(encoding="utf-8")
    m = re.search(r"_CHAT_MCP_TOOLS\s*=\s*\((.*?)\n\)", src, re.S)
    assert m, "未找到 _CHAT_MCP_TOOLS"
    listed = set(re.findall(r'"mcp__([a-z0-9_\-]+?)__', m.group(1)))
    unknown = sorted(
        n for n in listed
        if n not in configured
        and n.replace("_", "-") not in configured
        and n.replace("-", "_") not in configured
    )
    assert not unknown, f"允许清单含未配置的 MCP 服务器: {unknown}"
