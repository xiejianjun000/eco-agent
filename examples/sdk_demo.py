#!/usr/bin/env python3
"""
examples/sdk_demo.py — eco_agent_sdk 使用示例

前置：先启动 eco-server（eco server），再运行本脚本。

    python3 examples/sdk_demo.py
"""

from __future__ import annotations

import asyncio

from eco_agent_sdk import EcoClient


async def main() -> None:
    async with EcoClient("http://127.0.0.1:8788") as client:
        # 健康检查
        health = await client.health()
        print(f"[health] {health}")

        # 版本
        v = await client.version()
        print(f"[version] {v.version}")

        # 对话（非流式）
        resp = await client.chat("大气污染防治法对超标排放的处罚幅度是多少？")
        print(f"[chat] {resp.reply[:80]}...")

        # 对话（SSE 流式）
        print("[chat/stream] ", end="")
        async for chunk in client.chat_stream("用一句话介绍生态环境法典"):
            print(chunk, end="", flush=True)
        print()

        # 记忆树
        stats = await client.memory_stats()
        print(f"[memory] nodes={stats.total_nodes}, edges={stats.total_edges}")

        # 技能库
        skills = await client.list_skills()
        print(f"[skills] {len(skills)} 个技能")

        # 工具目录
        tools = await client.list_tools()
        cats = {t.category for t in tools}
        print(f"[tools] {len(tools)} 个工具, {len(cats)} 个分类")

        # 系统状态
        sys_status = await client.system()
        print(f"[system] components={list(sys_status.components.keys())}")


if __name__ == "__main__":
    asyncio.run(main())
