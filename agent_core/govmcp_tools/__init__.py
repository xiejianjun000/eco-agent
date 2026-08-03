#!/usr/bin/env python3
"""
agent_core/govmcp/tools/government/__init__.py
govmcp 政务工具集 - 工具注册入口

100+ 政务专用工具，分类注册到 GovMCPServer。
"""

from agent_core.govmcp.tools.registry import ToolRegistry, govmcp_tool

registry = ToolRegistry()

# ─── 懒加载注册 ───

def register_all(reg: ToolRegistry = None):
    """注册所有 govmcp 政务工具"""
    target = reg or registry

    # 环境监测工具 (15)
    try:
        from agent_core.govmcp_tools.environmental import register_environmental
        register_environmental(target)
    except ImportError:
        pass

    # 碳排放工具 (15)
    try:
        from agent_core.govmcp_tools.carbon_emission import register_carbon
        register_carbon(target)
    except ImportError:
        pass

    # 市民服务 (20)
    try:
        from agent_core.govmcp_tools.citizen_service import register_citizen
        register_citizen(target)
    except ImportError:
        pass

    # 企业服务 (20)
    try:
        from agent_core.govmcp_tools.enterprise_service import register_enterprise
        register_enterprise(target)
    except ImportError:
        pass

    # 智慧城市 (15)
    try:
        from agent_core.govmcp_tools.smart_city import register_smart_city
        register_smart_city(target)
    except ImportError:
        pass

    # 审批工作流 (15)
    try:
        from agent_core.govmcp_tools.approval_workflow import register_approval
        register_approval(target)
    except ImportError:
        pass

    return target


def get_tool_count() -> int:
    return registry.count()


def list_all() -> list:
    return registry.list_tools()
