"""FastMCP 服务入口。

用法：
  hunan-env-mcp                 # 默认 stdio 模式（供 Claude Desktop/Cursor 等客户端）
  hunan-env-mcp http            # Streamable HTTP 模式，监听 0.0.0.0:8000
"""

from __future__ import annotations

import logging
import sys

from mcp.server.fastmcp import FastMCP

from . import __version__
from .tools import air, gov, search

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

_INSTRUCTIONS = (
    "湖南省生态环境厅公开数据查询服务。数据来源：湖南省生态环境厅官网 "
    "(https://sthjt.hunan.gov.cn) 与省环境质量实时发布平台。"
    "空气质量实时数据为分钟级快照，政务栏目数据以官网发布为准。"
    "查询政务信息时优先使用对应栏目工具，实时空气数据可组合使用。"
)


def build_server(host: str | None = None, port: int | None = None) -> FastMCP:
    kwargs: dict = {"instructions": _INSTRUCTIONS}
    if host:
        kwargs["host"] = host
    if port:
        kwargs["port"] = port
    mcp = FastMCP("hunan-env", **kwargs)

    # ---- 空气质量（4） ----
    mcp.tool()(air.air_quality_realtime)
    mcp.tool()(air.air_quality_hourly)
    mcp.tool()(air.air_quality_forecast)
    mcp.tool()(air.air_quality_rank_daily)

    # ---- 政务栏目（14） ----
    mcp.tool()(gov.eia_publicity_search)
    mcp.tool()(gov.policy_document_search)
    mcp.tool()(gov.notice_announcement_list)
    mcp.tool()(gov.environmental_quality_monthly)
    mcp.tool()(gov.env_statistics_report)
    mcp.tool()(gov.enforcement_case_search)
    mcp.tool()(gov.credit_evaluation_query)
    mcp.tool()(gov.news_dynamic_list)
    mcp.tool()(gov.interaction_list)
    mcp.tool()(gov.key_domain_list)
    mcp.tool()(gov.legal_document_list)
    mcp.tool()(gov.management_public_list)
    mcp.tool()(gov.org_structure_list)
    mcp.tool()(gov.media_center_list)
    mcp.tool()(gov.document_detail)

    # ---- 站内检索（1） ----
    mcp.tool()(search.site_search)

    logger.info("hunan-env-mcp %s 已注册 %d 个工具", __version__, len(mcp._tool_manager._tools))
    return mcp


def main() -> None:
    server = build_server()
    if len(sys.argv) > 1 and sys.argv[1] == "http":
        host = "0.0.0.0"
        port = 8000
        if "--port" in sys.argv:
            port = int(sys.argv[sys.argv.index("--port") + 1])
        logger.info("启动 Streamable HTTP 模式: %s:%s", host, port)
        server = build_server(host=host, port=port)
        server.run(transport="streamable-http")
    else:
        logger.info("启动 stdio 模式")
        server.run()


if __name__ == "__main__":
    main()
