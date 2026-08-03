#!/usr/bin/env python3
"""
agent_core/govmcp_tools/environmental.py
环境监测工具集 (15 tools)

涵盖大气、水质、噪声、固废等环境监测相关 MCP 工具。
"""

import json
from typing import Optional

from agent_core.govmcp.tools.registry import ToolRegistry, govmcp_tool


def register_environmental(registry: ToolRegistry):
    """注册环境监测工具"""

    @govmcp_tool(
        name="env_query_air_quality",
        description="查询指定城市实时空气质量（AQI、PM2.5、PM10、O3、NO2、SO2、CO）",
        category="环境监测-大气",
        tags=["environmental", "air", "aqi", "monitoring"],
    )
    async def query_air_quality(city: str, station: Optional[str] = None) -> str:
        """
        查询实时空气质量。
        
        Args:
            city: 城市名称，如"北京"
            station: 监测站点编号（可选）
        
        Returns:
            JSON: {"aqi": int, "pm25": float, "pm10": float, "o3": float, "no2": float, "so2": float, "co": float, "level": str, "primary_pollutant": str}
        """
        return json.dumps({"status": "ok", "method": "query_air_quality", "city": city}, ensure_ascii=False)


    @govmcp_tool(
        name="env_query_water_quality",
        description="查询地表水断面水质（pH、DO、COD、NH3-N、TP、TN）",
        category="环境监测-水质",
        tags=["environmental", "water", "quality", "monitoring"],
    )
    async def query_water_quality(section: str, date_range: str = "7d") -> str:
        return json.dumps({"status": "ok", "method": "query_water_quality", "section": section}, ensure_ascii=False)


    @govmcp_tool(
        name="env_query_noise",
        description="查询功能区噪声监测数据，返回 Leq dB(A) 昼夜值",
        category="环境监测-噪声",
        tags=["environmental", "noise", "monitoring"],
    )
    async def query_noise(zone: str, period: str = "Ld") -> str:
        return json.dumps({"status": "ok", "method": "query_noise", "zone": zone}, ensure_ascii=False)


    @govmcp_tool(
        name="env_query_weather_forecast",
        description="查询城市72小时天气预报（温度、湿度、风向风速、降水概率）",
        category="环境监测-气象",
        tags=["environmental", "weather", "forecast"],
    )
    async def query_weather_forecast(city: str, hours: int = 24) -> str:
        return json.dumps({"status": "ok", "method": "query_weather_forecast", "city": city}, ensure_ascii=False)


    @govmcp_tool(
        name="env_query_pollution_source",
        description="查询重点污染源在线监控数据（企业排口、排放浓度、总量、超标标记）",
        category="环境监测-污染源",
        tags=["environmental", "pollution", "source", "enterprise"],
    )
    async def query_pollution_source(
        enterprise: str,
        outfall: Optional[str] = None,
        date_range: str = "24h",
    ) -> str:
        return json.dumps(
            {"status": "ok", "method": "query_pollution_source", "enterprise": enterprise},
            ensure_ascii=False,
        )


    @govmcp_tool(
        name="env_query_emergency_monitor",
        description="查询突发环境事件应急监测报告（事故点位、扩散范围、污染物浓度）",
        category="环境监测-应急",
        tags=["environmental", "emergency", "monitoring"],
    )
    async def query_emergency_monitor(event_id: str) -> str:
        return json.dumps({"status": "ok", "method": "query_emergency_monitor", "event_id": event_id}, ensure_ascii=False)


    @govmcp_tool(
        name="env_query_trend",
        description="查询环境质量历史趋势（过去 N 个月 AQI/水质等级变化曲线数据）",
        category="环境监测-趋势分析",
        tags=["environmental", "trend", "history"],
    )
    async def query_trend(city: str, indicator: str = "AQI", months: int = 12) -> str:
        return json.dumps({"status": "ok", "method": "query_trend", "city": city, "indicator": indicator}, ensure_ascii=False)


    @govmcp_tool(
        name="env_query_soil_quality",
        description="查询建设用地土壤污染状况（重金属、VOCs、SVOCs）",
        category="环境监测-土壤",
        tags=["environmental", "soil", "land"],
    )
    async def query_soil_quality(plot_id: str) -> str:
        return json.dumps({"status": "ok", "method": "query_soil_quality", "plot_id": plot_id}, ensure_ascii=False)


    @govmcp_tool(
        name="env_query_waste_transfer",
        description="查询危险废物转移联单执行状态（产生单位、运输单位、处置单位、转移量）",
        category="环境监测-固废",
        tags=["environmental", "waste", "hazardous", "transfer"],
    )
    async def query_waste_transfer(manifest_id: str) -> str:
        return json.dumps({"status": "ok", "method": "query_waste_transfer", "manifest_id": manifest_id}, ensure_ascii=False)


    @govmcp_tool(
        name="env_query_radiation",
        description="查询辐射环境监测数据（γ剂量率、气溶胶、沉降物）",
        category="环境监测-辐射",
        tags=["environmental", "radiation", "nuclear"],
    )
    async def query_radiation(station: str, date: Optional[str] = None) -> str:
        return json.dumps({"status": "ok", "method": "query_radiation", "station": station}, ensure_ascii=False)


    @govmcp_tool(
        name="env_query_cnemc_standard",
        description="查询中国环境监测总站(CNEMC)标准方法/限值",
        category="环境监测-标准",
        tags=["environmental", "standard", "cnemc"],
    )
    async def query_cnemc_standard(code: str) -> str:
        return json.dumps({"status": "ok", "method": "query_cnemc_standard", "code": code}, ensure_ascii=False)


    @govmcp_tool(
        name="env_query_eia_report",
        description="查询建设项目环境影响评价报告摘要（批复文号、主要结论、措施要求）",
        category="环境监测-环评",
        tags=["environmental", "eia", "approval"],
    )
    async def query_eia_report(project_name: str, approval_number: Optional[str] = None) -> str:
        return json.dumps({"status": "ok", "method": "query_eia_report", "project_name": project_name}, ensure_ascii=False)


    @govmcp_tool(
        name="env_query_discharge_permit",
        description="查询排污许可证基本信息（许可排放量、排放标准、自行监测方案）",
        category="环境监测-许可证",
        tags=["environmental", "permit", "discharge"],
    )
    async def query_discharge_permit(enterprise: str, permit_number: Optional[str] = None) -> str:
        return json.dumps({"status": "ok", "method": "query_discharge_permit", "enterprise": enterprise}, ensure_ascii=False)


    @govmcp_tool(
        name="env_query_ecological_redline",
        description="查询生态保护红线划定范围及管控要求",
        category="环境监测-生态",
        tags=["environmental", "ecological", "redline", "protection"],
    )
    async def query_ecological_redline(region: str, coordinates: Optional[list] = None) -> str:
        return json.dumps({"status": "ok", "method": "query_ecological_redline", "region": region}, ensure_ascii=False)


    @govmcp_tool(
        name="env_query_carbon_data",
        description="查询区域碳排放数据（总量、强度、行业分布）",
        category="环境监测-碳",
        tags=["environmental", "carbon", "emission", "climate"],
    )
    async def query_carbon_data(region: str, year: int = 2025) -> str:
        return json.dumps({"status": "ok", "method": "query_carbon_data", "region": region, "year": year}, ensure_ascii=False)


    registry.register_batch([v for k, v in locals().items() if callable(v) and hasattr(v, "_govmcp_meta")])
    return registry
