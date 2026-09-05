"""空气质量类 MCP 工具（数据源：hn.leitesoft.cn:9020 HNAirWebAPI）。"""

from __future__ import annotations

from ..datasource import air_api


def air_quality_realtime(region: str | None = None) -> list[dict]:
    """查询湖南省各市州及全省的实时空气质量（AQI、等级、首要污染物）。

    Args:
        region: 可选，市州名称（如 长沙、株洲）或"全省"；不传返回全部。

    Returns:
        每个站点一条记录，含站点名/AQI/等级/首要污染物/查询时间。
    """
    return air_api.air_realtime(region)


def air_quality_hourly(city: str) -> list[dict]:
    """查询指定城市逐小时空气质量序列。

    Args:
        city: 必填，市州名称，如 长沙、株洲。

    Returns:
        逐小时 AQI 记录列表。
    """
    return air_api.air_hourly(city)


def air_quality_forecast() -> list[dict]:
    """查询最新一期湖南省城市空气质量预报/预警信息。无参数。"""
    return air_api.air_forecast()


def air_quality_rank_daily(begin_date: str, end_date: str) -> list[dict]:
    """按日查询湖南省城市空气质量排名。

    Args:
        begin_date: 开始日期，格式 YYYY-MM-DD。
        end_date: 结束日期，格式 YYYY-MM-DD。

    Returns:
        城市按日排名记录列表。
    """
    return air_api.air_rank_daily(begin_date, end_date)
