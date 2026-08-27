#!/usr/bin/env python3
"""
govmcp_tools/citizen_service.py
市民服务工具集 (20 tools)
"""

import json

from govmcp.tools.registry import ToolRegistry, govmcp_tool


def register_citizen(registry: ToolRegistry):
    """注册市民服务工具"""

    @govmcp_tool(
        name="citizen_query_id_card",
        description="查询居民身份证办理进度（受理、制证、发放）",
        category="市民服务-证件",
        tags=["citizen", "id_card", "service"],
    )
    async def query_id_card(tracking_number: str) -> str:
        return json.dumps({"status": "ok", "method": "query_id_card"}, ensure_ascii=False)

    @govmcp_tool(
        name="citizen_query_household",
        description="查询户籍业务办理状态（迁入/迁出/出生登记/注销）",
        category="市民服务-户籍",
        tags=["citizen", "household", "residence"],
    )
    async def query_household(application_id: str) -> str:
        return json.dumps({"status": "ok", "method": "query_household"}, ensure_ascii=False)

    @govmcp_tool(
        name="citizen_query_social_security",
        description="查询个人社保缴纳记录（养老/医疗/失业/工伤/生育）",
        category="市民服务-社保",
        tags=["citizen", "social_security", "insurance"],
    )
    async def query_social_security(id_number: str, year: int = 2025) -> str:
        return json.dumps({"status": "ok", "method": "query_social_security"}, ensure_ascii=False)

    @govmcp_tool(
        name="citizen_query_medical_insurance",
        description="查询医保账户余额、消费明细、报销进度",
        category="市民服务-医保",
        tags=["citizen", "medical", "insurance", "health"],
    )
    async def query_medical_insurance(id_number: str) -> str:
        return json.dumps({"status": "ok", "method": "query_medical_insurance"}, ensure_ascii=False)

    @govmcp_tool(
        name="citizen_query_housing_fund",
        description="查询住房公积金账户（缴存基数、余额、贷款信息）",
        category="市民服务-公积金",
        tags=["citizen", "housing", "fund", "provident"],
    )
    async def query_housing_fund(id_number: str) -> str:
        return json.dumps({"status": "ok", "method": "query_housing_fund"}, ensure_ascii=False)

    @govmcp_tool(
        name="citizen_query_education",
        description="查询学籍信息、学历认证、考试报名状态",
        category="市民服务-教育",
        tags=["citizen", "education", "enrollment"],
    )
    async def query_education(id_number: str, query_type: str = "enrollment") -> str:
        return json.dumps({"status": "ok", "method": "query_education"}, ensure_ascii=False)

    @govmcp_tool(
        name="citizen_query_vehicle",
        description="查询机动车登记信息（号牌、检验有效期、违章记录）",
        category="市民服务-交管",
        tags=["citizen", "vehicle", "traffic"],
    )
    async def query_vehicle(plate_number: str) -> str:
        return json.dumps({"status": "ok", "method": "query_vehicle"}, ensure_ascii=False)

    @govmcp_tool(
        name="citizen_query_driver_license",
        description="查询驾驶证信息（准驾车型、有效期、记分情况）",
        category="市民服务-交管",
        tags=["citizen", "driver", "license"],
    )
    async def query_driver_license(license_number: str) -> str:
        return json.dumps({"status": "ok", "method": "query_driver_license"}, ensure_ascii=False)

    @govmcp_tool(
        name="citizen_query_marriage",
        description="查询婚姻登记预约/进度/档案",
        category="市民服务-民政",
        tags=["citizen", "marriage", "registration"],
    )
    async def query_marriage(application_id: str | None = None) -> str:
        return json.dumps({"status": "ok", "method": "query_marriage"}, ensure_ascii=False)

    @govmcp_tool(
        name="citizen_query_birth_registration",
        description="查询出生医学证明及户籍登记进度",
        category="市民服务-民政",
        tags=["citizen", "birth", "registration"],
    )
    async def query_birth_registration(certificate_number: str) -> str:
        return json.dumps({"status": "ok", "method": "query_birth_registration"}, ensure_ascii=False)

    @govmcp_tool(
        name="citizen_query_death_certificate",
        description="查询死亡证明及户籍注销状态",
        category="市民服务-民政",
        tags=["citizen", "death", "certificate"],
    )
    async def query_death_certificate(certificate_number: str) -> str:
        return json.dumps({"status": "ok", "method": "query_death_certificate"}, ensure_ascii=False)

    @govmcp_tool(
        name="citizen_query_property_rights",
        description="查询不动产权属证书（房屋/土地登记信息）",
        category="市民服务-不动产",
        tags=["citizen", "property", "title", "real_estate"],
    )
    async def query_property_rights(certificate_number: str) -> str:
        return json.dumps({"status": "ok", "method": "query_property_rights"}, ensure_ascii=False)

    @govmcp_tool(
        name="citizen_query_tax_record",
        description="查询个人所得税申报/缴纳记录",
        category="市民服务-税务",
        tags=["citizen", "tax", "income"],
    )
    async def query_tax_record(id_number: str, year: int = 2025) -> str:
        return json.dumps({"status": "ok", "method": "query_tax_record"}, ensure_ascii=False)

    @govmcp_tool(
        name="citizen_query_disability_benefits",
        description="查询残疾人补贴发放记录（困难生活补贴/重度护理补贴）",
        category="市民服务-残联",
        tags=["citizen", "disability", "benefits"],
    )
    async def query_disability_benefits(id_number: str) -> str:
        return json.dumps({"status": "ok", "method": "query_disability_benefits"}, ensure_ascii=False)

    @govmcp_tool(
        name="citizen_query_subsistence_allowance",
        description="查询低保金发放状态（最低生活保障）",
        category="市民服务-民政",
        tags=["citizen", "subsistence", "allowance", "dibao"],
    )
    async def query_subsistence_allowance(id_number: str) -> str:
        return json.dumps({"status": "ok", "method": "query_subsistence_allowance"}, ensure_ascii=False)

    @govmcp_tool(
        name="citizen_query_pension",
        description="查询养老金发放明细（企业职工/城乡居民/机关事业）",
        category="市民服务-养老",
        tags=["citizen", "pension", "retirement"],
    )
    async def query_pension(id_number: str, year: int = 2025) -> str:
        return json.dumps({"status": "ok", "method": "query_pension"}, ensure_ascii=False)

    @govmcp_tool(
        name="citizen_query_certificate",
        description="查询电子证照库（出生证/身份证/结婚证/不动产证/营业执照等）",
        category="市民服务-证照",
        tags=["citizen", "certificate", "digital", "e-cert"],
    )
    async def query_certificate(cert_type: str, id_number: str) -> str:
        return json.dumps({"status": "ok", "method": "query_certificate"}, ensure_ascii=False)

    @govmcp_tool(
        name="citizen_query_appointment",
        description="查询政务服务大厅预约状态（窗口业务、排队人数）",
        category="市民服务-预约",
        tags=["citizen", "appointment", "queue", "service_hall"],
    )
    async def query_appointment(hall_id: str, business_type: str) -> str:
        return json.dumps({"status": "ok", "method": "query_appointment"}, ensure_ascii=False)

    @govmcp_tool(
        name="citizen_query_complaint",
        description="查询政务投诉/信访工单办理进度（12345热线）",
        category="市民服务-投诉",
        tags=["citizen", "complaint", "12345", "petition"],
    )
    async def query_complaint(ticket_id: str) -> str:
        return json.dumps({"status": "ok", "method": "query_complaint"}, ensure_ascii=False)

    @govmcp_tool(
        name="citizen_query_business_license",
        description="查询营业执照信息（个体工商户/企业/合作社）",
        category="市民服务-工商",
        tags=["citizen", "business_license", "registration"],
    )
    async def query_business_license(credit_code: str) -> str:
        return json.dumps({"status": "ok", "method": "query_business_license"}, ensure_ascii=False)

    registry.register_batch([v for k, v in locals().items() if callable(v) and hasattr(v, "_govmcp_meta")])
    return registry
