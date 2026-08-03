#!/usr/bin/env python3
"""
agent_core/govmcp_tools/smart_city.py
智慧城市工具集 (15 tools)
"""

import json
from typing import Optional

from agent_core.govmcp.tools.registry import ToolRegistry, govmcp_tool


def register_smart_city(registry: ToolRegistry):
    """注册智慧城市工具"""

    @govmcp_tool(
        name="smart_query_public_transport",
        description="查询城市公交/地铁实时到站信息及线路规划",
        category="智慧城市-交通",
        tags=["smart_city", "transit", "bus", "metro"],
    )
    async def query_public_transport(city: str, line: str, direction: str = "up") -> str:
        return json.dumps({"status": "ok", "method": "query_public_transport"}, ensure_ascii=False)

    @govmcp_tool(
        name="smart_query_traffic_congestion",
        description="查询城市道路拥堵指数及实时路况",
        category="智慧城市-交通",
        tags=["smart_city", "traffic", "congestion"],
    )
    async def query_traffic_congestion(city: str, road_section: Optional[str] = None) -> str:
        return json.dumps({"status": "ok", "method": "query_traffic_congestion"}, ensure_ascii=False)

    @govmcp_tool(
        name="smart_query_parking",
        description="查询智慧停车场实时空位数及收费标准",
        category="智慧城市-停车",
        tags=["smart_city", "parking", "lot"],
    )
    async def query_parking(city: str, location: Optional[str] = None) -> str:
        return json.dumps({"status": "ok", "method": "query_parking"}, ensure_ascii=False)

    @govmcp_tool(
        name="smart_query_street_lamp",
        description="查询智能路灯运行状态（亮灯率、故障告警、能耗）",
        category="智慧城市-照明",
        tags=["smart_city", "street_lamp", "lighting", "IoT"],
    )
    async def query_street_lamp(area: str) -> str:
        return json.dumps({"status": "ok", "method": "query_street_lamp"}, ensure_ascii=False)

    @govmcp_tool(
        name="smart_query_waste_management",
        description="查询智慧环卫垃圾桶满溢状态及清运路线",
        category="智慧城市-环卫",
        tags=["smart_city", "waste", "sanitation", "IoT"],
    )
    async def query_waste_management(area: str) -> str:
        return json.dumps({"status": "ok", "method": "query_waste_management"}, ensure_ascii=False)

    @govmcp_tool(
        name="smart_query_water_supply",
        description="查询智慧水务管网压力、水质在线监测",
        category="智慧城市-水务",
        tags=["smart_city", "water", "supply", "pipeline"],
    )
    async def query_water_supply(monitoring_point: str) -> str:
        return json.dumps({"status": "ok", "method": "query_water_supply"}, ensure_ascii=False)

    @govmcp_tool(
        name="smart_query_gas_supply",
        description="查询智慧燃气管网运行数据（压力、流量、泄漏告警）",
        category="智慧城市-燃气",
        tags=["smart_city", "gas", "supply", "pipeline"],
    )
    async def query_gas_supply(monitoring_point: str) -> str:
        return json.dumps({"status": "ok", "method": "query_gas_supply"}, ensure_ascii=False)

    @govmcp_tool(
        name="smart_query_power_grid",
        description="查询智能电网负荷及分布式能源信息",
        category="智慧城市-能源",
        tags=["smart_city", "power", "grid", "energy"],
    )
    async def query_power_grid(area: str, time_range: str = "1h") -> str:
        return json.dumps({"status": "ok", "method": "query_power_grid"}, ensure_ascii=False)

    @govmcp_tool(
        name="smart_query_city_camera",
        description="查询公共安全视频监控点位及实时截图（需权限审批）",
        category="智慧城市-安防",
        tags=["smart_city", "camera", "surveillance", "public_safety"],
    )
    async def query_city_camera(camera_id: str, approval_id: str) -> str:
        return json.dumps({"status": "ok", "method": "query_city_camera"}, ensure_ascii=False)

    @govmcp_tool(
        name="smart_query_emergency_response",
        description="查询城市应急响应状态（自然灾害预警、避难场所、救援力量）",
        category="智慧城市-应急",
        tags=["smart_city", "emergency", "disaster", "response"],
    )
    async def query_emergency_response(city: str) -> str:
        return json.dumps({"status": "ok", "method": "query_emergency_response"}, ensure_ascii=False)

    @govmcp_tool(
        name="smart_query_city_governance",
        description="查询城市运行管理服务平台工单（网格化管理、部件事件上报）",
        category="智慧城市-治理",
        tags=["smart_city", "governance", "grid", "urban_management"],
    )
    async def query_city_governance(ticket_id: str) -> str:
        return json.dumps({"status": "ok", "method": "query_city_governance"}, ensure_ascii=False)

    @govmcp_tool(
        name="smart_query_digital_twin",
        description="查询城市数字孪生三维模型（BIM/CIM 建筑物信息）",
        category="智慧城市-数字孪生",
        tags=["smart_city", "digital_twin", "bim", "cim", "3d"],
    )
    async def query_digital_twin(building_id: str, layer: str = "architectural") -> str:
        return json.dumps({"status": "ok", "method": "query_digital_twin"}, ensure_ascii=False)

    @govmcp_tool(
        name="smart_query_open_data",
        description="查询政府开放数据目录（人口/经济/地理/环境等公共数据集）",
        category="智慧城市-数据开放",
        tags=["smart_city", "open_data", "dataset", "catalog"],
    )
    async def query_open_data(category: str = "economy", format: str = "json") -> str:
        return json.dumps({"status": "ok", "method": "query_open_data"}, ensure_ascii=False)

    @govmcp_tool(
        name="smart_query_city_app_service",
        description="查询城市服务APP功能入口（水电缴费、社保查询、公积金等）",
        category="智慧城市-便民",
        tags=["smart_city", "app", "service", "mobile"],
    )
    async def query_city_app_service(city: str, service_type: str = "utilities") -> str:
        return json.dumps({"status": "ok", "method": "query_city_app_service"}, ensure_ascii=False)

    @govmcp_tool(
        name="smart_query_iot_device",
        description="查询物联网设备运行状态（NB-IoT/LoRa传感器、空气质量微站）",
        category="智慧城市-IoT",
        tags=["smart_city", "iot", "sensor", "device"],
    )
    async def query_iot_device(device_id: str) -> str:
        return json.dumps({"status": "ok", "method": "query_iot_device"}, ensure_ascii=False)

    registry.register_batch([v for k, v in locals().items() if callable(v) and hasattr(v, "_govmcp_meta")])
    return registry
