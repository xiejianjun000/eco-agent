#!/usr/bin/env python3
"""
govmcp.tools.government.environmental — 环保监测工具模块

提供空气质量、水质、土壤、噪声、固废等环境监测和环保监管服务的工具函数。
"""

from typing import Any

from govmcp.tools.government._demo import demo_govmcp_tool as govmcp_tool
from govmcp.tools.government.cnemc import (
    CNEMCError,
    get_city_realtime_air_quality,
)


@govmcp_tool(
    name="query_air_quality",
    description="查询空气质量监测数据",
)
def query_air_quality(
    region: str,
    monitoring_station: str,
    date: str,
) -> dict[str, Any]:
    """
    查询空气质量实时数据(中国环境监测总站 CNEMC 官方数据)。

    直连"全国城市空气质量实时发布平台"(air.cnemc.cn:18007), 返回实时
    6 参数(PM2.5/PM10/SO2/NO2/CO/O3) + AQI + 首要污染物 + 发布时间。
    城市名支持模糊匹配(如 "娄底"/"娄底市")。平台不可达时自动降级为
    最近一次缓存并标注 data_source="cache"; 无缓存则返回错误,
    绝不返回虚构数据冒充实时数据。

    Args:
        region: 城市名称(全国地市级城市)
        monitoring_station: 监测站点(保留参数, 实时接口按城市全市站点聚合)
        date: 查询日期(保留参数, 实时接口返回当前最新发布数据)

    Returns:
        空气质量数据, 含 data_source(cnemc_realtime/cache) 与 publish_time
    """
    try:
        result = get_city_realtime_air_quality(region)
    except CNEMCError as exc:
        return {
            "status": "error",
            "error": str(exc),
            "data": {
                "region": region,
                "monitoring_station": monitoring_station,
                "date": date,
                "data_source": "unavailable",
            },
        }
    return {
        "status": "success",
        "data": {
            "region": region,
            "monitoring_station": monitoring_station,
            "date": date,
            **result,
        },
    }


@govmcp_tool(
    name="query_water_quality",
    description="查询水质监测数据",
)
def query_water_quality(
    river_name: str,
    section_name: str,
    date: str,
) -> dict[str, Any]:
    """
    查询水质监测数据。

    Args:
        river_name: 河流名称
        section_name: 断面名称
        date: 查询日期

    Returns:
        水质监测数据
    """
    return {
        "status": "success",
        "data": {
            "river_name": river_name,
            "section_name": section_name,
            "date": date,
            "water_quality_class": "III类",
            "ph": 7.2,
            "dissolved_oxygen": 6.5,
            "cod": 15.0,
            "ammonia_nitrogen": 0.8,
            "total_phosphorus": 0.1,
            "total_nitrogen": 1.2,
            "status": "达标",
        },
    }


@govmcp_tool(
    name="detect_soil_pollution",
    description="土壤污染检测",
)
def detect_soil_pollution(
    location: str,
    land_use: str,
    sampling_date: str,
) -> dict[str, Any]:
    """
    土壤污染状况检测查询。

    Args:
        location: 地块位置
        land_use: 土地利用类型
        sampling_date: 采样日期

    Returns:
        土壤污染检测结果
    """
    return {
        "status": "success",
        "data": {
            "location": location,
            "land_use": land_use,
            "sampling_date": sampling_date,
            "heavy_metals": {
                "cadmium": 0.15,
                "mercury": 0.08,
                "arsenic": 8.5,
                "lead": 35.0,
            },
            "organic_matter": 2.5,
            "pollution_level": "轻度污染",
            "remediation_required": True,
        },
    }


@govmcp_tool(
    name="query_noise_monitoring",
    description="查询噪声监测数据",
)
def query_noise_monitoring(
    monitoring_point: str,
    date: str,
    time_period: str,
) -> dict[str, Any]:
    """
    查询环境噪声监测数据。

    Args:
        monitoring_point: 监测点位
        date: 查询日期
        time_period: 时段 (昼间/夜间)

    Returns:
        噪声监测数据
    """
    return {
        "status": "success",
        "data": {
            "monitoring_point": monitoring_point,
            "date": date,
            "time_period": time_period,
            "equivalent_sound_level": 55.5,
            "max_sound_level": 72.0,
            "min_sound_level": 42.0,
            "standard_limit": 60.0,
            "status": "达标",
        },
    }


@govmcp_tool(
    name="query_solid_waste_disposal",
    description="查询固废处理监管信息",
)
def query_solid_waste_disposal(
    company_name: str,
    waste_type: str,
) -> dict[str, Any]:
    """
    查询固体废物处理处置监管信息。

    Args:
        company_name: 企业名称
        waste_type: 废物类型 (一般固废/危险废物)

    Returns:
        固废处理监管信息
    """
    return {
        "status": "success",
        "data": {
            "company_name": company_name,
            "waste_type": waste_type,
            "monthly_output": 500.0,
            "monthly_disposal": 480.0,
            "storage_amount": 20.0,
            "disposal_method": "卫生填埋",
            "disposal_company": "XX固废处理有限公司",
            "next_inspection_date": "2026-06-15",
            "status": "正常",
        },
    }


@govmcp_tool(
    name="query_hazardous_waste_transfer",
    description="查询危险废物转移联单",
)
def query_hazardous_waste_transfer(
    manifest_no: str,
) -> dict[str, Any]:
    """
    查询危险废物转移联单信息。

    Args:
        manifest_no: 转移联单编号

    Returns:
        危废转移联单信息
    """
    return {
        "status": "success",
        "data": {
            "manifest_no": manifest_no,
            "waste_category": "HW08(废矿物油)",
            "quantity": 5.0,
            "unit": "吨",
            "transfer_date": "2026-05-10",
            "generator": "XX汽车维修有限公司",
            "transporter": "XX危险货物运输公司",
            "receiver": "XX危险废物处理中心",
            "status": "已完成",
        },
    }


@govmcp_tool(
    name="query_radiation_monitoring",
    description="查询辐射环境监测数据",
)
def query_radiation_monitoring(
    monitoring_location: str,
    monitoring_type: str,
    date: str,
) -> dict[str, Any]:
    """
    查询辐射环境监测数据。

    Args:
        monitoring_location: 监测地点
        monitoring_type: 监测类型 (γ辐射/氡/电磁辐射)
        date: 监测日期

    Returns:
        辐射监测数据
    """
    return {
        "status": "success",
        "data": {
            "monitoring_location": monitoring_location,
            "monitoring_type": monitoring_type,
            "date": date,
            "ambient_dose_rate": 0.08,
            "unit": "μSv/h",
            "standard_limit": 0.2,
            "status": "正常",
            "nearby_sources": [],
        },
    }


@govmcp_tool(
    name="query_pollution_discharge_permit",
    description="查询排污许可证信息",
)
def query_pollution_discharge_permit(
    company_name: str,
    permit_no: str,
) -> dict[str, Any]:
    """
    查询企业排污许可证信息。

    Args:
        company_name: 企业名称
        permit_no: 许可证编号

    Returns:
        排污许可证信息
    """
    return {
        "status": "success",
        "data": {
            "company_name": company_name,
            "permit_no": permit_no,
            "permit_type": "重点管理",
            "issue_date": "2024-06-01",
            "valid_until": "2027-05-31",
            "emission_limits": {
                "so2": 50.0,
                "nox": 100.0,
                "particulate": 30.0,
                "cod": 500.0,
                "ammonia_nitrogen": 45.0,
            },
            "status": "有效",
        },
    }


@govmcp_tool(
    name="query_environmental_impact_assessment",
    description="查询环境影响评价信息",
)
def query_environmental_impact_assessment(
    project_name: str,
    eia_document_no: str,
) -> dict[str, Any]:
    """
    查询环境影响评价信息。

    Args:
        project_name: 项目名称
        eia_document_no: 环评批复文号

    Returns:
        环评信息
    """
    return {
        "status": "success",
        "data": {
            "project_name": project_name,
            "document_no": eia_document_no,
            "eia_category": "报告表",
            "approval_authority": "XX市生态环境局",
            "approval_date": "2025-08-15",
            "main_environmental_impacts": ["废气排放", "噪声影响"],
            "main_protection_measures": ["脱硫脱硝", "隔声降噪"],
            "status": "批复有效",
        },
    }


@govmcp_tool(
    name="query_environmental_penalty",
    description="查询环保处罚记录",
)
def query_environmental_penalty(
    company_name: str,
    region: str,
) -> dict[str, Any]:
    """
    查询企业环保行政处罚记录。

    Args:
        company_name: 企业名称
        region: 地区

    Returns:
        处罚记录列表
    """
    return {
        "status": "success",
        "data": {
            "company_name": company_name,
            "region": region,
            "total_violations": 0,
            "records": [],
            "compliance_rate": 100.0,
        },
    }


@govmcp_tool(
    name="apply_cleaner_production_audit",
    description="申请清洁生产审核",
)
def apply_cleaner_production_audit(
    company_name: str,
    industry: str,
    production_scale: str,
) -> dict[str, Any]:
    """
    申请清洁生产审核。

    Args:
        company_name: 企业名称
        industry: 行业类型
        production_scale: 生产规模

    Returns:
        审核申请结果
    """
    return {
        "status": "success",
        "data": {
            "application_id": f"CPA{20260513001}",
            "company_name": company_name,
            "industry": industry,
            "production_scale": production_scale,
            "audit_organization": "XX清洁生产审核中心",
            "estimated_start_date": "2026-06-01",
            "estimated_duration": "6个月",
            "status": "受理中",
        },
    }


@govmcp_tool(
    name="query_environmental_acceptance",
    description="查询环保竣工验收信息",
)
def query_environmental_acceptance(
    project_name: str,
    acceptance_no: str,
) -> dict[str, Any]:
    """
    查询建设项目竣工环境保护验收信息。

    Args:
        project_name: 项目名称
        acceptance_no: 验收备案号

    Returns:
        环保竣工验收信息
    """
    return {
        "status": "success",
        "data": {
            "project_name": project_name,
            "acceptance_no": acceptance_no,
            "acceptance_date": "2025-12-20",
            "acceptance_type": "验收监测",
            "conclusion": "通过",
            "pollution_control_effect": "合格",
            "environmental_protection_facilities": "正常运行",
            "status": "验收合格",
        },
    }


@govmcp_tool(
    name="query_environmental_facility_operation",
    description="查询环保设施运行数据",
)
def query_environmental_facility_operation(
    company_name: str,
    facility_type: str,
) -> dict[str, Any]:
    """
    查询企业环保设施运行数据。

    Args:
        company_name: 企业名称
        facility_type: 设施类型 (废气处理/废水处理/噪声控制)

    Returns:
        环保设施运行数据
    """
    return {
        "status": "success",
        "data": {
            "company_name": company_name,
            "facility_type": facility_type,
            "facility_name": "XX废气处理设施",
            "operation_rate": 98.5,
            "treatment_efficiency": 92.0,
            "daily_treatment_capacity": 50000.0,
            "actual_treatment": 48000.0,
            "equipment_status": "正常运行",
            "last_maintenance_date": "2026-04-15",
            "next_maintenance_date": "2026-07-15",
        },
    }


@govmcp_tool(
    name="query_ecological_red_line",
    description="查询生态红线保护区信息",
)
def query_ecological_red_line(
    location: str,
) -> dict[str, Any]:
    """
    查询区域生态红线保护信息。

    Args:
        location: 地理位置

    Returns:
        生态红线信息
    """
    return {
        "status": "success",
        "data": {
            "location": location,
            "within_red_line": False,
            "nearest_red_line_distance": "5公里",
            "red_line_zones": [
                {
                    "name": "XX国家森林公园",
                    "area": 5000.0,
                    "distance": "8公里",
                },
            ],
            "development_restrictions": "距生态红线500米范围内的开发活动需进行生态影响评价",
        },
    }


@govmcp_tool(
    name="query_environmental_emergency_response",
    description="查询环境应急响应信息",
)
def query_environmental_emergency_response(
    company_name: str,
) -> dict[str, Any]:
    """
    查询企业环境应急响应相关信息。

    Args:
        company_name: 企业名称

    Returns:
        环境应急响应信息
    """
    return {
        "status": "success",
        "data": {
            "company_name": company_name,
            "emergency_plan_recorded": True,
            "emergency_plan_no": "XX应急备字[2025]第XX号",
            "emergency_facilities": ["围堰", "事故应急池", "切断阀"],
            "emergency_materials": ["吸油棉", "中和剂", "应急监测设备"],
            "last_drill_date": "2026-03-20",
            "next_drill_date": "2026-09-20",
            "status": "预案有效",
        },
    }
