"""全国排污许可证管理信息平台公开端 MCP Server 启动入口。

运行：
    python server.py
或（使用 uv）：
    uv run server.py

客户端可通过 MCP 标准协议连接，暴露工具：
    search_licenses / get_license_detail / get_license_pages / download_license_page
    get_qrcode_info / get_post_permit_status / get_rectification / get_announcements
    list_policy_docs / get_policy_detail / get_discharge_points / get_monitoring_data
"""

from fastmcp import FastMCP

from permit_mcp import config
from permit_mcp.tools import register_tools


def create_server() -> FastMCP:
    mcp = FastMCP(
        "全国排污许可证公开端",
        version="0.1.0",
        instructions=(
            "全国排污许可证管理信息平台公开端穿透式数据服务。"
            "可查询任意企业排污许可证正副本、排放口点位、证后管理（执行报告/监督执法/自行监测）、"
            "限期整改、注销撤销公告与政策法规全文。"
        ),
    )
    register_tools(mcp)
    return mcp


def main() -> None:
    mcp = create_server()
    mcp.run()


if __name__ == "__main__":
    main()
