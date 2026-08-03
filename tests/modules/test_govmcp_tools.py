#!/usr/bin/env python3
"""
tests/modules/test_govmcp_tools.py
govmcp 工具集成测试
"""

from agent_core.govmcp.tools.registry import ToolRegistry


def test_registry_create():
    """测试工具注册表创建"""
    reg = ToolRegistry()
    assert reg is not None
    assert reg.count() >= 0


def test_registry_register_single():
    """测试单工具注册"""
    from agent_core.govmcp.tools.registry import govmcp_tool

    reg = ToolRegistry()

    @govmcp_tool(name="test_hello", description="测试工具", category="测试")
    async def hello():
        return "hello"

    reg.register(hello)
    assert reg.count() == 1
    assert "test_hello" in reg.list_tools()


def test_full_registration():
    """测试全量工具注册"""
    from agent_core.govmcp_tools.environmental import register_environmental
    from agent_core.govmcp_tools.carbon_emission import register_carbon
    from agent_core.govmcp_tools.citizen_service import register_citizen
    from agent_core.govmcp_tools.enterprise_service import register_enterprise
    from agent_core.govmcp_tools.smart_city import register_smart_city
    from agent_core.govmcp_tools.approval_workflow import register_approval

    reg = ToolRegistry()
    register_environmental(reg)
    register_carbon(reg)
    register_citizen(reg)
    register_enterprise(reg)
    register_smart_city(reg)
    register_approval(reg)

    count = reg.count()
    reg.list_tools()

    assert count >= 100, f"Expected at least 100 tools, got {count}"
    print(f"[PASS] Registered {count} govmcp tools")


def test_tool_execution():
    """测试工具调用"""
    import asyncio

    async def run():
        from agent_core.govmcp_tools.environmental import register_environmental

        reg = ToolRegistry()
        register_environmental(reg)

        tool = reg.get("env_query_air_quality")
        assert tool is not None

        result = await tool(city="北京")
        assert "aqi" in result.lower() or "ok" in result.lower()

    asyncio.run(run())


if __name__ == "__main__":
    test_full_registration()
    test_tool_execution()
    print("All govmcp tools tests passed.")
