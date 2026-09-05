#!/usr/bin/env python3
"""
govmcp_tools/__init__.py
govmcp 政务工具集 - 工具注册入口

100+ 政务专用工具，分类注册到 GovMCPServer。
"""

from govmcp.tools.registry import ToolRegistry, govmcp_tool

__all__ = ["ToolRegistry", "govmcp_tool", "registry", "register_all", "get_tool_count", "list_all"]

registry = ToolRegistry()

# ─── 懒加载注册 ───


def register_all(reg: ToolRegistry = None):
    """注册所有 govmcp 政务工具"""
    target = reg or registry

    # 环境监测工具 (15)
    try:
        from govmcp_tools.environmental import register_environmental

        register_environmental(target)
    except ImportError:
        pass

    # 碳排放工具 (15)
    try:
        from govmcp_tools.carbon_emission import register_carbon

        register_carbon(target)
    except ImportError:
        pass

    # 市民服务 (20)
    try:
        from govmcp_tools.citizen_service import register_citizen

        register_citizen(target)
    except ImportError:
        pass

    # 企业服务 (20)
    try:
        from govmcp_tools.enterprise_service import register_enterprise

        register_enterprise(target)
    except ImportError:
        pass

    # 智慧城市 (15)
    try:
        from govmcp_tools.smart_city import register_smart_city

        register_smart_city(target)
    except ImportError:
        pass

    # 审批工作流 (15)
    try:
        from govmcp_tools.approval_workflow import register_approval

        register_approval(target)
    except ImportError:
        pass

    # 执法平台-污染源在线监测（娄底市重点污染源自动监控，博安达平台）(11)
    try:
        from govmcp_tools.wryzxjc import register_wryzxjc

        register_wryzxjc(target)
    except ImportError:
        pass

    # 执法平台-国家四平台（综合执法监管：规范涉企检查/行政处罚/水环境）(17)
    try:
        from govmcp_tools.sthjzf import register_sthjzf

        register_sthjzf(target)
    except ImportError:
        pass

    # 环境公开数据源（地表水自动站/空气质量预报，实测端点）(2)
    try:
        from govmcp_tools.env_open_data import register_env_open_data

        register_env_open_data(target)
    except ImportError:
        pass

    # 湖南省厅环境质量月报（静态HTML全文解析，实测路线）(1)
    try:
        from govmcp_tools.hunan_env import register_hunan_env

        register_hunan_env(target)
    except ImportError:
        pass

    # 执法平台-排污许可管理（全国排污许可证管理信息平台-管理端，只读）(11)
    try:
        from govmcp_tools.permit_management import register_permit

        register_permit(target)
    except ImportError:
        pass

    return target


def get_tool_count() -> int:
    return registry.count()


def list_all() -> list:
    return registry.list_tools()
