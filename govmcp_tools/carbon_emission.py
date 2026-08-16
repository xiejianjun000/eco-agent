#!/usr/bin/env python3
"""
govmcp_tools/carbon_emission.py
碳排放管理工具集 (15 tools)
"""

import json

from govmcp.tools.registry import ToolRegistry, govmcp_tool


def register_carbon(registry: ToolRegistry):
    """注册碳排放管理工具"""

    @govmcp_tool(
        name="carbon_query_enterprise_emission",
        description="查询企业年度碳排放报告（核算总量、配额、履约状态）",
        category="碳排放-企业核算",
        tags=["carbon", "emission", "enterprise", "report"],
    )
    async def query_enterprise_emission(enterprise: str, year: int = 2025) -> str:
        return json.dumps({"status": "ok", "method": "query_enterprise_emission", "enterprise": enterprise}, ensure_ascii=False)

    @govmcp_tool(
        name="carbon_query_quota",
        description="查询企业碳排放配额分配情况（免费配额、拍卖配额、CCER使用上限）",
        category="碳排放-配额",
        tags=["carbon", "quota", "allocation"],
    )
    async def query_quota(enterprise: str, year: int = 2025) -> str:
        return json.dumps({"status": "ok", "method": "query_quota", "enterprise": enterprise}, ensure_ascii=False)

    @govmcp_tool(
        name="carbon_query_trading",
        description="查询全国碳市场交易行情（CEA价格、成交量、涨跌幅）",
        category="碳排放-交易",
        tags=["carbon", "trading", "market", "cea"],
    )
    async def query_trading(date: str | None = None) -> str:
        return json.dumps({"status": "ok", "method": "query_trading"}, ensure_ascii=False)

    @govmcp_tool(
        name="carbon_submit_verification",
        description="提交碳排放报告核查申请（第三方核查机构、核查周期）",
        category="碳排放-核查",
        tags=["carbon", "verification", "submit"],
    )
    async def submit_verification(enterprise: str, report_id: str, verifier: str) -> str:
        return json.dumps({"status": "ok", "method": "submit_verification", "enterprise": enterprise}, ensure_ascii=False)

    @govmcp_tool(
        name="carbon_query_offset_project",
        description="查询CCER减排项目信息（项目类型、减排量、签发状态）",
        category="碳排放-CCER",
        tags=["carbon", "ccer", "offset", "project"],
    )
    async def query_offset_project(project_id: str) -> str:
        return json.dumps({"status": "ok", "method": "query_offset_project", "project_id": project_id}, ensure_ascii=False)

    @govmcp_tool(
        name="carbon_calculate_footprint",
        description="计算产品碳足迹（原材料→生产→运输→使用→废弃）",
        category="碳排放-碳足迹",
        tags=["carbon", "footprint", "product", "lifecycle"],
    )
    async def calculate_footprint(product: str, boundary: str = "cradle-to-gate") -> str:
        return json.dumps({"status": "ok", "method": "calculate_footprint", "product": product}, ensure_ascii=False)

    @govmcp_tool(
        name="carbon_query_baseline",
        description="查询行业碳排放基准值（发电/钢铁/水泥/化工等）",
        category="碳排放-基准",
        tags=["carbon", "baseline", "industry", "benchmark"],
    )
    async def query_baseline(industry: str, year: int = 2025) -> str:
        return json.dumps({"status": "ok", "method": "query_baseline", "industry": industry}, ensure_ascii=False)

    @govmcp_tool(
        name="carbon_query_policy",
        description="查询碳达峰碳中和政策法规（国家/省/市三级）",
        category="碳排放-政策",
        tags=["carbon", "policy", "peaking", "neutrality"],
    )
    async def query_policy(level: str = "national", keyword: str | None = None) -> str:
        return json.dumps({"status": "ok", "method": "query_policy"}, ensure_ascii=False)

    @govmcp_tool(
        name="carbon_submit_annual_report",
        description="提交企业年度碳排放报告（核算方法学、活动数据、排放因子）",
        category="碳排放-报告",
        tags=["carbon", "annual", "report", "submit"],
    )
    async def submit_annual_report(enterprise: str, year: int, data: dict) -> str:
        return json.dumps({"status": "ok", "method": "submit_annual_report", "enterprise": enterprise}, ensure_ascii=False)

    @govmcp_tool(
        name="carbon_query_compliance",
        description="查询企业碳市场履约情况（清缴率、欠缴量、处罚记录）",
        category="碳排放-履约",
        tags=["carbon", "compliance", "clearance"],
    )
    async def query_compliance(enterprise: str, year: int = 2025) -> str:
        return json.dumps({"status": "ok", "method": "query_compliance", "enterprise": enterprise}, ensure_ascii=False)

    @govmcp_tool(
        name="carbon_query_emission_factor",
        description="查询官方碳排放因子数据库（电力/燃料/原料/运输）",
        category="碳排放-因子",
        tags=["carbon", "factor", "database", "emission"],
    )
    async def query_emission_factor(category: str = "electricity", region: str | None = None) -> str:
        return json.dumps({"status": "ok", "method": "query_emission_factor", "category": category}, ensure_ascii=False)

    @govmcp_tool(
        name="carbon_query_esg_score",
        description="查询企业ESG评级及环境维度评分详情",
        category="碳排放-ESG",
        tags=["carbon", "esg", "rating", "score"],
    )
    async def query_esg_score(enterprise: str, agency: str = "msci") -> str:
        return json.dumps({"status": "ok", "method": "query_esg_score", "enterprise": enterprise}, ensure_ascii=False)

    @govmcp_tool(
        name="carbon_query_green_bond",
        description="查询绿色债券发行信息（募集用途、环境效益、认证）",
        category="碳排放-绿色金融",
        tags=["carbon", "green", "bond", "finance"],
    )
    async def query_green_bond(issuer: str | None = None, year: int = 2025) -> str:
        return json.dumps({"status": "ok", "method": "query_green_bond"}, ensure_ascii=False)

    @govmcp_tool(
        name="carbon_query_technology",
        description="查询低碳技术推荐目录（CCUS、节能、新能源替代方案）",
        category="碳排放-技术",
        tags=["carbon", "technology", "low-carbon", "ccus"],
    )
    async def query_technology(industry: str, scenario: str = "emission_reduction") -> str:
        return json.dumps({"status": "ok", "method": "query_technology", "industry": industry}, ensure_ascii=False)

    @govmcp_tool(
        name="carbon_submit_offset_application",
        description="提交CCER抵消申请（用于企业配额清缴）",
        category="碳排放-抵消",
        tags=["carbon", "offset", "ccer", "application"],
    )
    async def submit_offset_application(enterprise: str, project_id: str, quantity: int) -> str:
        return json.dumps({"status": "ok", "method": "submit_offset_application", "enterprise": enterprise}, ensure_ascii=False)

    registry.register_batch([v for k, v in locals().items() if callable(v) and hasattr(v, "_govmcp_meta")])
    return registry
