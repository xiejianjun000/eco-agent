#!/usr/bin/env python3
"""
govmcp_tools/env_open_data.py — 环境公开数据源工具（P0-2 数据源版图）
====================================================================
两个经实测验证的 CNEMC 公开端点（2026-08-23 实测 HTTP 200 真实数据）：

1. 国家地表水水质自动监测实时数据
   POST https://szzdjc.cnemc.cn:8070/GJZ/Ajax/Publish.ashx
   body: action=getRealDatas&AreaID=&RiverID=&MNName=&PageIndex=1&PageSize=10
   返回省份/流域/断面/水质类别/水温/pH/溶解氧/氨氮/总磷/总氮等
2. 空气质量预报（区域级）
   GET https://air.cnemc.cn:18014/AreaForecast/ChangeArea?areaCode=900001&strForecastType=1
   areaCode: 900001全国/900010京津冀/900020长三角/900030珠三角/900040东北/
             900060西北/900070西南/900092华南/900093天山北坡

契约：httpx 客户端、10s 超时、失败降级（无缓存即报错，绝不编造数据）。
"""

from __future__ import annotations

from typing import Any

import httpx
import urllib3

from govmcp.tools.registry import ToolRegistry, govmcp_tool

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

WATER_URL = "https://szzdjc.cnemc.cn:8070/GJZ/Ajax/Publish.ashx"
FORECAST_URL = "https://air.cnemc.cn:18014/AreaForecast/ChangeArea"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

AREA_NAMES = {
    "900001": "全国", "900010": "京津冀及周边", "900020": "长三角",
    "900021": "汾渭平原", "900030": "珠三角", "900040": "东北",
    "900060": "西北", "900070": "西南", "900092": "华南", "900093": "天山北坡",
}

CATEGORY = "环境数据-公开数据源"
TAGS = ["环境数据", "CNEMC", "地表水", "自动站", "空气质量预报", "公开数据"]


def _client() -> httpx.Client:
    return httpx.Client(timeout=10.0, verify=False,
                        headers={"User-Agent": UA,
                                 "Referer": "https://szzdjc.cnemc.cn:8070/"})


@govmcp_tool(
    name="water_station_realtime",
    description="国家地表水水质自动监测实时数据(实测端点)。river流域名(如海河流域),mn_name断面名称模糊查询,page_index页码。返回断面水质类别/水温/pH/溶解氧/氨氮/总磷/总氮等",
    category=CATEGORY,
    tags=TAGS,
)
def water_station_realtime(river: str = "", mn_name: str = "",
                           page_index: int = 1, page_size: int = 10) -> dict:
    """地表水自动站实时数据（实测端点，约 20 分钟刷新）。"""
    body = {"action": "getRealDatas", "AreaID": "", "RiverID": river,
            "MNName": mn_name, "PageIndex": str(page_index),
            "PageSize": str(page_size)}
    try:
        with _client() as c:
            r = c.post(WATER_URL, data=body)
            r.raise_for_status()
            j = r.json()
        if j.get("result") != 1:
            return {"success": False, "error": f"接口返回异常: {str(j)[:200]}"}
        return {"success": True, "total": j.get("total"),
                "records": j.get("records"), "thead": j.get("thead"),
                "tbody": (j.get("tbody") or [])[:page_size],
                "source": "szzdjc.cnemc.cn:8070 实测端点"}
    except Exception as e:  # noqa: BLE001
        return {"success": False, "error": f"获取失败: {e}"}


@govmcp_tool(
    name="air_forecast",
    description="空气质量预报(区域级,实测端点)。area_code区域码:900001全国/900010京津冀及周边/900020长三角/900030珠三角/900040东北/900060西北/900070西南/900092华南/900093天山北坡",
    category=CATEGORY,
    tags=TAGS,
)
def air_forecast(area_code: str = "900001") -> dict:
    """空气质量区域预报（未来五天文字预报 + 首要污染物）。"""
    try:
        with _client() as c:
            r = c.get(FORECAST_URL,
                      params={"areaCode": area_code, "strForecastType": "1"})
            r.raise_for_status()
            j = r.json()
        return {"success": True, "area": AREA_NAMES.get(area_code, area_code),
                "forecast": j.get("ForecastDescription", "")[:600],
                "publish_date": j.get("PublishDateText", ""),
                "source": "air.cnemc.cn:18014 实测端点"}
    except Exception as e:  # noqa: BLE001
        return {"success": False, "error": f"获取失败: {e}"}


_TOOLS: list[Any] = [water_station_realtime, air_forecast]


def register_env_open_data(reg: ToolRegistry) -> ToolRegistry:
    """注册环境公开数据源工具。"""
    reg.register_batch(_TOOLS)
    return reg


# ─── 聊天通道暴露 ──────────────────────────────────────────────

def _p(props: dict, required: list[str]) -> dict:
    return {"type": "object", "properties": props, "required": required}


CHAT_TOOLS: dict[str, dict] = {
    "water_station_realtime": {
        "description": "国家地表水水质自动监测实时数据（实测公开端点）：按流域/断面查询水质类别、pH、溶解氧、氨氮、总磷、总氮。",
        "parameters": _p(
            {
                "river": {"type": "string", "description": "流域名（如 海河流域，空=全部）"},
                "mn_name": {"type": "string", "description": "断面名称模糊查询"},
                "page_index": {"type": "integer", "description": "页码（默认1）"},
                "page_size": {"type": "integer", "description": "每页条数（默认10）"},
            },
            [],
        ),
        "handler": water_station_realtime,
    },
    "air_forecast": {
        "description": "空气质量区域预报（实测公开端点）：未来五天扩散条件与首要污染物。area_code 默认 900001 全国。",
        "parameters": _p(
            {"area_code": {"type": "string", "description": "区域码（900001全国/900010京津冀/900020长三角/900030珠三角等）"}},
            [],
        ),
        "handler": air_forecast,
    },
}

CHAT_NAMES: list[str] = list(CHAT_TOOLS.keys())
