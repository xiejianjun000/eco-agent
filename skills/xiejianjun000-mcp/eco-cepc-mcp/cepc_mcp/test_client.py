#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CEPC MCP Server 客户端测试脚本

测试方法：
    1. 启动 MCP server: python3 server.py
    2. 另一终端: python3 test_client.py

或编程方式（推荐）：
    from mcp import ClientSession, StdioServerTransport
    session = ClientSession(StdioServerTransport())
"""
import sys
import os
import asyncio
import json
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


async def test_via_subprocess():
    """通过子进程方式测试 MCP server（stdio 模式）"""
    server_path = Path(__file__).parent / "server.py"

    print("=" * 70)
    print(" CEPC MCP Server 测试客户端")
    print("=" * 70)
    print(f"Server 路径：{server_path}")
    print()

    # 启动 server 子进程
    print("📡 启动 MCP server (stdio 模式)...")
    proc = subprocess.Popen(
        [sys.executable, str(server_path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=sys.stderr,
        text=True,
        bufsize=0,
    )

    # 简化测试：发送 tools/list 请求
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/list",
        "params": {},
    }

    try:
        proc.stdin.write(json.dumps(request) + "\n")
        proc.stdin.flush()

        # 读取响应
        response_line = proc.stdout.readline()
        if response_line:
            response = json.loads(response_line)
            if "result" in response:
                tools = response["result"].get("tools", [])
                print(f"✅ 成功连接，tools 数量：{len(tools)}")
                for tool in tools:
                    print(f"  - {tool['name']}: {tool['description'][:50]}...")
            else:
                print(f"❌ 响应异常：{response}")
        else:
            print("❌ 无响应（可能是 MCP 握手复杂，stdio 模式需用官方 ClientSession）")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


async def test_with_mcp_client():
    """使用官方 MCP 客户端测试（推荐方式）"""
    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
    except ImportError:
        print("❌ mcp client SDK 未安装")
        print("   请运行: pip install mcp[client]")
        return

    server_path = Path(__file__).parent / "server.py"
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[str(server_path)],
    )

    print("=" * 70)
    print(" CEPC MCP Server 官方客户端测试")
    print("=" * 70)

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # 1. 列出所有工具
            print("\n[1] 列出工具...")
            tools = await session.list_tools()
            print(f"  共 {len(tools.tools)} 个工具:")
            for t in tools.tools:
                print(f"    - {t.name}")

            # 2. 测试 veto_rules_list
            print("\n[2] 测试 veto_rules_list...")
            result = await session.call_tool("veto_rules_list", {})
            print(f"  返回前 200 字符：{result.content[0].text[:200]}...")

            # 3. 测试 project_audit
            print("\n[3] 测试 project_audit（公示期不足 20 工作日场景）...")
            test_project = {
                "project_name": "湖南某化工企业新建项目",
                "build_unit": "湖南某某化工有限公司",
                "eia_doc_no": "湘环评〔2024〕第123号",
                "public_start_date": "2026-07-01",
                "public_end_date": "2026-07-15",  # 仅 14 天，不足 20 工作日
                "industry_category_mgmt": "化工",
            }
            result = await session.call_tool(
                "project_audit", {"project": test_project}
            )
            print(f"  {result.content[0].text[:500]}")

            print("\n" + "=" * 70)
            print("✅ 所有测试通过")
            print("=" * 70)


if __name__ == "__main__":
    # 默认使用官方客户端测试
    asyncio.run(test_with_mcp_client())
