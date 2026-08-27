#!/usr/bin/env python3
"""
govmcp_tools/enterprise_service.py
企业服务工具集 (20 tools)
"""

import json

from govmcp.tools.registry import ToolRegistry, govmcp_tool


def register_enterprise(registry: ToolRegistry):
    """注册企业服务工具"""

    @govmcp_tool(
        name="enterprise_query_registration",
        description="查询企业工商注册信息（统一社会信用代码、注册资本、经营范围、股东）",
        category="企业服务-登记",
        tags=["enterprise", "registration", "credit_code"],
    )
    async def query_registration(credit_code: str) -> str:
        return json.dumps({"status": "ok", "method": "query_registration"}, ensure_ascii=False)

    @govmcp_tool(
        name="enterprise_query_tax_info",
        description="查询企业税务登记信息（纳税人识别号、纳税信用等级）",
        category="企业服务-税务",
        tags=["enterprise", "tax", "credit_rating"],
    )
    async def query_tax_info(credit_code: str) -> str:
        return json.dumps({"status": "ok", "method": "query_tax_info"}, ensure_ascii=False)

    @govmcp_tool(
        name="enterprise_query_customs",
        description="查询企业海关备案信息（报关代码、AEO认证等级）",
        category="企业服务-海关",
        tags=["enterprise", "customs", "aeo", "import_export"],
    )
    async def query_customs(credit_code: str) -> str:
        return json.dumps({"status": "ok", "method": "query_customs"}, ensure_ascii=False)

    @govmcp_tool(
        name="enterprise_query_food_license",
        description="查询食品生产/经营许可证（有效期、许可范围、日常监督检查结果）",
        category="企业服务-食药",
        tags=["enterprise", "food", "license", "production"],
    )
    async def query_food_license(permit_number: str) -> str:
        return json.dumps({"status": "ok", "method": "query_food_license"}, ensure_ascii=False)

    @govmcp_tool(
        name="enterprise_query_pharma_license",
        description="查询药品生产/经营许可证及GMP/GSP认证",
        category="企业服务-食药",
        tags=["enterprise", "pharmaceutical", "gmp", "gsp"],
    )
    async def query_pharma_license(license_number: str) -> str:
        return json.dumps({"status": "ok", "method": "query_pharma_license"}, ensure_ascii=False)

    @govmcp_tool(
        name="enterprise_query_construction_permit",
        description="查询建筑工程施工许可证（项目名称、建设单位、施工单位、许可范围）",
        category="企业服务-建设",
        tags=["enterprise", "construction", "permit", "building"],
    )
    async def query_construction_permit(permit_number: str) -> str:
        return json.dumps({"status": "ok", "method": "query_construction_permit"}, ensure_ascii=False)

    @govmcp_tool(
        name="enterprise_query_trademark",
        description="查询商标注册信息（申请号、类别、状态、专用权期限）",
        category="企业服务-知识产权",
        tags=["enterprise", "trademark", "ip", "brand"],
    )
    async def query_trademark(application_number: str) -> str:
        return json.dumps({"status": "ok", "method": "query_trademark"}, ensure_ascii=False)

    @govmcp_tool(
        name="enterprise_query_patent",
        description="查询专利信息（申请号、发明名称、法律状态、权利人）",
        category="企业服务-知识产权",
        tags=["enterprise", "patent", "ip", "invention"],
    )
    async def query_patent(application_number: str) -> str:
        return json.dumps({"status": "ok", "method": "query_patent"}, ensure_ascii=False)

    @govmcp_tool(
        name="enterprise_query_credit_report",
        description="查询企业信用报告（行政处罚、经营异常、严重失信、司法案件）",
        category="企业服务-信用",
        tags=["enterprise", "credit", "report", "blacklist"],
    )
    async def query_credit_report(credit_code: str) -> str:
        return json.dumps({"status": "ok", "method": "query_credit_report"}, ensure_ascii=False)

    @govmcp_tool(
        name="enterprise_query_subsidy",
        description="查询企业可申报的政府补贴/奖励项目（产业扶持、科技创新、稳岗返还）",
        category="企业服务-补贴",
        tags=["enterprise", "subsidy", "grant", "government"],
    )
    async def query_subsidy(industry: str, scale: str = "SME") -> str:
        return json.dumps({"status": "ok", "method": "query_subsidy"}, ensure_ascii=False)

    @govmcp_tool(
        name="enterprise_query_bidding",
        description="查询政府采购/工程招标公告（项目预算、资质要求、投标截止时间）",
        category="企业服务-招投标",
        tags=["enterprise", "bidding", "procurement", "tender"],
    )
    async def query_bidding(keyword: str, region: str | None = None) -> str:
        return json.dumps({"status": "ok", "method": "query_bidding"}, ensure_ascii=False)

    @govmcp_tool(
        name="enterprise_query_statistics",
        description="查询行业统计公报（产值、增速、就业人数等）",
        category="企业服务-统计",
        tags=["enterprise", "statistics", "industry", "macro"],
    )
    async def query_statistics(industry: str, year: int = 2025) -> str:
        return json.dumps({"status": "ok", "method": "query_statistics"}, ensure_ascii=False)

    @govmcp_tool(
        name="enterprise_query_inspection",
        description="查询双随机一公开抽查结果（检查部门、检查内容、整改要求）",
        category="企业服务-监管",
        tags=["enterprise", "inspection", "random", "regulatory"],
    )
    async def query_inspection(credit_code: str, year: int = 2025) -> str:
        return json.dumps({"status": "ok", "method": "query_inspection"}, ensure_ascii=False)

    @govmcp_tool(
        name="enterprise_query_foreign_trade",
        description="查询外贸企业进出口数据（HS编码、贸易国别、货值）",
        category="企业服务-外贸",
        tags=["enterprise", "trade", "import", "export", "hs_code"],
    )
    async def query_foreign_trade(credit_code: str, year: int = 2025) -> str:
        return json.dumps({"status": "ok", "method": "query_foreign_trade"}, ensure_ascii=False)

    @govmcp_tool(
        name="enterprise_query_special_industry",
        description="查询特殊行业许可证（危化品/采矿/烟花爆竹/民用爆炸物品）",
        category="企业服务-特殊行业",
        tags=["enterprise", "special", "license", "hazardous"],
    )
    async def query_special_industry(license_number: str) -> str:
        return json.dumps({"status": "ok", "method": "query_special_industry"}, ensure_ascii=False)

    @govmcp_tool(
        name="enterprise_query_environmental_penalty",
        description="查询企业环境行政处罚记录（处罚原因、罚款金额、整改要求）",
        category="企业服务-环保",
        tags=["enterprise", "environmental", "penalty", "administrative"],
    )
    async def query_environmental_penalty(credit_code: str) -> str:
        return json.dumps({"status": "ok", "method": "query_environmental_penalty"}, ensure_ascii=False)

    @govmcp_tool(
        name="enterprise_query_work_safety",
        description="查询安全生产许可证及事故记录",
        category="企业服务-安全",
        tags=["enterprise", "safety", "production", "accident"],
    )
    async def query_work_safety(license_number: str) -> str:
        return json.dumps({"status": "ok", "method": "query_work_safety"}, ensure_ascii=False)

    @govmcp_tool(
        name="enterprise_query_labor_dispute",
        description="查询企业劳动仲裁/争议案件（案由、裁决结果）",
        category="企业服务-人社",
        tags=["enterprise", "labor", "dispute", "arbitration"],
    )
    async def query_labor_dispute(credit_code: str) -> str:
        return json.dumps({"status": "ok", "method": "query_labor_dispute"}, ensure_ascii=False)

    @govmcp_tool(
        name="enterprise_query_annual_report",
        description="查询企业年度报告公示信息（资产总额、负债、利润、纳税）",
        category="企业服务-工商",
        tags=["enterprise", "annual_report", "disclosure"],
    )
    async def query_annual_report(credit_code: str, year: int = 2024) -> str:
        return json.dumps({"status": "ok", "method": "query_annual_report"}, ensure_ascii=False)

    @govmcp_tool(
        name="enterprise_query_change_record",
        description="查询企业工商变更记录（股东/法人/注册资本/经营范围变更）",
        category="企业服务-工商",
        tags=["enterprise", "change", "record", "amendment"],
    )
    async def query_change_record(credit_code: str) -> str:
        return json.dumps({"status": "ok", "method": "query_change_record"}, ensure_ascii=False)

    registry.register_batch([v for k, v in locals().items() if callable(v) and hasattr(v, "_govmcp_meta")])
    return registry
