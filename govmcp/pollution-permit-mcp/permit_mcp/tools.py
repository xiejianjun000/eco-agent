"""MCP 工具定义：全国排污许可证公开端全量数据读取。"""

from __future__ import annotations

import json
import time
from typing import Any

from fastmcp import FastMCP

from . import config
from .client import PermitClient
from .parser import (decrypt_point_data, parse_announce_list, parse_license_detail,
                     parse_license_list, parse_laws_list, parse_news_detail,
                     parse_news_list, parse_post_permit_status)

_client: PermitClient | None = None


def get_client() -> PermitClient:
    global _client
    if _client is None:
        _client = PermitClient()
    return _client


def _out(data: Any) -> str:
    """统一输出为紧凑 JSON 字符串（兼容 MCP 文本返回）。"""
    return json.dumps(data, ensure_ascii=False, indent=1)


def register_tools(mcp: FastMCP) -> None:
    c = get_client()

    # ---------- 1. 许可信息公开查询 ----------
    @mcp.tool()
    def search_licenses(
        province: str = "",
        city: str = "",
        unit_name: str = "",
        license_no: str = "",
        industry: str = "",
        page: int = 1,
    ) -> str:
        """按省/市/单位名/许可证编号/行业分页查询全国排污许可证（公开端，无需登录）。

        Args:
            province: 省份，如"河北省"（留空表示全国）
            city: 地市
            unit_name: 企业名称关键字
            license_no: 排污许可证编号（如 91110108MA001XXXXX001V）
            industry: 行业类别
            page: 页码，从 1 开始
        """
        data = {
            "province": province, "city": city, "unitName": unit_name,
            "licenseNumber": license_no, "industry": industry,
            "pageIndex": page, "pageSize": 20,
        }
        html = c.post(config.URL_LICENSE_LIST, data=data)
        return _out(parse_license_list(html))

    # ---------- 2. 许可证详情 ----------
    @mcp.tool()
    def get_license_detail(dataid: str) -> str:
        """获取企业排污许可证详情：基本信息、许可证正本版本、副本摘要、经纬度、排放口点位。

        Args:
            dataid: 数据 ID（由 search_licenses 返回，32 位十六进制）
        """
        html = c.get(config.URL_LICENSE_DETAIL, params={"xkgk": "getxxgkContent", "dataid": dataid})
        return _out(parse_license_detail(html))

    # ---------- 3. 副本图片页列表 ----------
    @mcp.tool()
    def get_license_pages(dataid: str) -> str:
        """获取排污许可证副本图片清单（页数与每页 datafileid），供 OCR 还原全文。

        Args:
            dataid: 数据 ID
        """
        html = c.get(config.URL_LICENSE_IMAGE_LIST, params={"dataid": dataid})
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        img_count = soup.find("input", {"id": "imgCount"})
        pkid = soup.find("input", {"id": "pkid"})
        if img_count is None or pkid is None:
            return _out({"total_pages": 0, "pages": [], "error": "页面未找到 imgCount/pkid"})
        n = int(img_count.get("value") or 0)
        pid = pkid.get("value") or ""
        pages = [{"page": i + 1, "datafileid": f"{pid}_{i + 1}"} for i in range(n)]
        return _out({"total_pages": n, "pkid": pid, "pages": pages})

    # ---------- 4. 副本页图片下载 ----------
    @mcp.tool()
    def download_license_page(dataid: str, datafileid: str, output_path: str) -> str:
        """下载排污许可证副本指定页 PNG 到本地，供 OCR。

        Args:
            dataid: 数据 ID（get_license_pages 返回的 pkid 对应同一许可证）
            datafileid: 形如 <pkid>_<页码> 的文件 ID（get_license_pages 返回）
            output_path: 保存图片的绝对路径
        """
        content = c.download(config.URL_LICENSE_IMAGE_PAGE,
                             params={"datafileid": datafileid, "fileType": "pdffile",
                                     "dataid": dataid})
        with open(output_path, "wb") as f:
            f.write(content)
        return _out({"saved": output_path, "bytes": len(content)})

    # ---------- 5. 排放口二维码 ----------
    @mcp.tool()
    def get_qrcode_info(dataid: str) -> str:
        """生成排放口二维码（平台二维码接口，内容为许可证详情地址）。

        Args:
            dataid: 数据 ID
        """
        url = f"{config.URL_QRCODE}/{dataid}"
        return _out({"qrcode_url": url, "note": "扫码可查看该企业排污许可公开信息"})

    # ---------- 6. 证后管理状态 ----------
    @mcp.tool()
    def get_post_permit_status(dataid: str) -> str:
        """获取证后管理实时情况：执行报告（年度/季度报告文档链接）、自行监测入口。

        Args:
            dataid: 数据 ID
        """
        import datetime
        reports = []
        now_year = datetime.date.today().year
        for year in range(now_year, now_year - 3, -1):
            resp = c.post(config.URL_ZXBG_YEAR,
                          data={"reportYear": str(year), "dataid": dataid})
            try:
                rows = json.loads(resp)
            except Exception:  # noqa: BLE001
                rows = []
            for r in rows:
                reports.append({"year": str(year), "type": r.get("type"),
                                "report_time": r.get("reportTime"), "doc_url": r.get("docUrl")})
        result = {"execution_reports": reports, "supervision": [],
                  "monitoring_url": None}
        # 自行监测入口（详情页 iframe）
        html = c.get(config.URL_LICENSE_DETAIL, params={"xkgk": "getxxgkContent", "dataid": dataid})
        import re
        m = re.search(r'<iframe[^>]+src="(https://wryjc\.mee\.gov\.cn[^"]+)"', html)
        if m:
            result["monitoring_url"] = m.group(1)
            result["monitoring_note"] = "自行监测信息由全国污染源监测信息管理共享平台提供（wryjc.mee.gov.cn）"
        return _out(result)

    # ---------- 7. 限期整改 ----------
    @mcp.tool()
    def get_rectification(province: str = "", unit_name: str = "", page: int = 1) -> str:
        """查询限期整改公示列表。

        Args:
            province: 省份
            unit_name: 企业名称
            page: 页码
        """
        data = {"province": province, "unitName": unit_name, "pageIndex": page, "pageSize": 20}
        html = c.post(config.URL_RECTIFY_LIST, data=data)
        return _out(parse_news_list(html))

    # ---------- 8. 公告（注销/撤销/遗失） ----------
    @mcp.tool()
    def get_announcements(announce_type: str = "注销", page: int = 1) -> str:
        """查询排污许可证公告：注销、撤销、遗失声明。

        Args:
            announce_type: 注销 / 撤销 / 遗失
            page: 页码
        """
        url = {
            "注销": config.URL_ANNOUNCE_CANCEL,
            "撤销": config.URL_ANNOUNCE_REVOKE,
            "遗失": config.URL_ANNOUNCE_LOST,
        }.get(announce_type)
        if not url:
            return _out({"error": "announce_type 仅支持：注销/撤销/遗失"})
        data = {"province": "", "unitName": "", "pageIndex": page, "pageSize": 20}
        html = c.post(url, data=data)
        return _out(parse_announce_list(html))

    # ---------- 9. 政策法规列表 ----------
    @mcp.tool()
    def list_policy_docs(category: str = "Law", page: int = 1) -> str:
        """按分类列出环保政策法规/标准目录。

        Args:
            category: Law=法律法规, XKJSGF=许可技术规范, SSHYPFBZ=实施行业排放标准,
                      HYKXJSZN=行业可行技术指南, HYZXJCZN=行业自行监测指南, XKJGYQ=许可监管要求
            page: 页码
        """
        data = {"columntype": category, "pageIndex": page, "pageSize": 20}
        html = c.post(config.URL_LAWS_LIST, data=data)
        return _out(parse_laws_list(html))

    # ---------- 10. 政策法规全文 ----------
    @mcp.tool()
    def get_policy_detail(pkid: str) -> str:
        """获取政策法规/新闻/公告全文（明文正文 + 附件下载链接）。

        Args:
            pkid: 文档 ID（list_policy_docs / get_announcements 返回）
        """
        html = c.get(config.URL_NEWS_DETAIL, params={"pkid": pkid})
        return _out(parse_news_detail(html))

    # ---------- 11. 排放口点位解密（辅助） ----------
    @mcp.tool()
    def get_discharge_points(dataid: str) -> str:
        """解密并返回企业排放口经纬度点位坐标数组（AES-128-ECB，密钥来自详情页内联脚本）。

        Args:
            dataid: 数据 ID
        """
        html = c.get(config.URL_LICENSE_DETAIL, params={"xkgk": "getxxgkContent", "dataid": dataid})
        points = decrypt_point_data(html)
        return _out({"point_count": len(points), "points": points})

    # ---------- 12. 证后管理监控接口（对接 wryjc 平台） ----------
    @mcp.tool()
    def get_monitoring_data(dataid: str) -> str:
        """返回企业自行监测信息对接地址（全国污染源监测信息管理共享平台）。

        Args:
            dataid: 数据 ID
        """
        html = c.get(config.URL_LICENSE_DETAIL, params={"xkgk": "getxxgkContent", "dataid": dataid})
        import re
        m = re.search(r'<iframe[^>]+src="(https://wryjc\.mee\.gov\.cn[^"]+)"', html)
        if m:
            return _out({"monitoring_url": m.group(1),
                         "note": "实时排放数据属自动监控专网，公开端不直接提供；请通过该平台查询"})
        return _out({"monitoring_url": None, "note": "该企业未配置自行监测信息"})
