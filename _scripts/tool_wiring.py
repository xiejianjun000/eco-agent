#!/usr/bin/env python3
"""
tool_wiring.py — 工具接线治理报告（对标 DSH inspect 契约目录）

回答三个问题：
  1. 注册表 108 个工具里，哪些真的接进了聊天通道（wired_in_chat）？
  2. 哪些有真实 handler 但没接线（has_handler_unwired）？
  3. 哪些只有 schema 定义、没有实现（def_only = 占位/待实现）？

用法：
  python _scripts/tool_wiring.py            # 全量报告
  python _scripts/tool_wiring.py --short    # 只列可行动项
"""

import argparse
import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def chat_tool_names() -> set[str]:
    """聊天通道实际暴露给 LLM 的工具名（server/api/chat.py 工具清单）。"""
    from server.api.chat import _codex_tools

    return {t["function"]["name"] for t in _codex_tools()}


def registry_view() -> tuple[list[str], set[str], set[str]]:
    """(全部工具名, 有 handler 的, MCP 远程的)"""
    from agent_core.tools_registry import _HANDLERS, ALL_TOOL_DEFS

    names = [d["function"]["name"] for d in ALL_TOOL_DEFS]
    handled = set(_HANDLERS.keys())
    mcp = {n for n in names if n.startswith("mcp__")}
    return names, handled, mcp


def handler_lines(name: str) -> int:
    try:
        from agent_core.tools_registry import _HANDLERS

        return len(inspect.getsource(_HANDLERS[name]).splitlines())
    except Exception:
        return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--short", action="store_true")
    args = ap.parse_args()

    names, handled, mcp = registry_view()
    wired = chat_tool_names()

    wired_list = sorted(wired)
    unwired = sorted(n for n in handled if n not in wired and n not in mcp)
    def_only = sorted(n for n in names if n not in handled and n not in mcp)

    print("=" * 66)
    print(f"工具接线治理报告 · 注册 {len(names)} · 有实现 {len(handled)} · MCP {len(mcp)} · 已接聊天 {len(wired)}")
    print("=" * 66)

    if not args.short:
        print(f"\n[已接聊天通道] {len(wired)}")
        for n in wired_list:
            print(f"  ✅ {n} ({handler_lines(n)} 行实现)")

    print(f"\n[有实现但未接聊天] {len(unwired)}")
    for n in unwired:
        print(f"  ⚠️  {n} ({handler_lines(n)} 行实现)")

    print(f"\n[只有定义无实现(占位)] {len(def_only)}")
    for n in def_only:
        print(f"  ⬜ {n}")

    print(f"\n[MCP 远程工具] {len(mcp)}（经 ECO_MCP_SERVERS 挂载，不入接线讨论）")

    from agent_core.wiring_manifest import WIRED_REQUIRED

    missing = [n for n in WIRED_REQUIRED if n not in wired]
    if missing:
        print(f"\n❌ 接线清单缺口（WIRED_REQUIRED 未接线）: {missing}")
        return 1
    print(f"\n✅ 接线清单全部就位（WIRED_REQUIRED {len(WIRED_REQUIRED)} 项）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
