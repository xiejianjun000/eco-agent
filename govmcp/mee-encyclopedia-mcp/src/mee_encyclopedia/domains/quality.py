"""环境质量领域：公报/年报/月报等质量报告的统一读取与导览。

报告列表复用 news.read_mee_list 统一栏目读取；本模块提供：
- 报告类型元数据（类型 -> 栏目名）
- 报告导览 list_quality_reports
- 报告读取 read_quality_report（含 PDF 公报提示）
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# 报告类型 -> 对应 news.CATEGORY_URLS 中的栏目名
REPORT_TYPES: dict[str, str] = {
    "生态环境状况公报": "生态环境状况公报",
    "生态环境统计年报": "生态环境统计年报",
    "海洋生态环境状况公报": "海洋公报",
    "噪声污染防治报告": "噪声防治报告",
    "固废污染环境防治年报": "固废年报",
    "移动源环境管理年报": "移动源年报",
    "地表水水质月报": "地表水水质月报",
    "全国地表水质量状况": "全国地表水质量状况",
    "海水浴场水质概况": "海水浴场水质",
    "全国空气质量状况": "全国空气质量状况",
    "空气质量预报": "空气质量预报",
    "城市空气质量报告": "城市空气质量报告",
}

# 以 PDF 附件为主、列表页主要是下载链接的报告类型
PDF_DOMINANT = {"生态环境状况公报", "生态环境统计年报", "海洋生态环境状况公报", "固废污染环境防治年报"}


def list_quality_reports() -> dict:
    """列出全部可读环境质量报告类型。"""
    return {
        "count": len(REPORT_TYPES),
        "reports": [
            {"type": t, "category": c, "pdf_dominant": t in PDF_DOMINANT}
            for t, c in REPORT_TYPES.items()
        ],
        "note": "使用 read_quality_report(report_type=...) 读取对应报告最新列表",
    }


def read_quality_report(fetcher, cache, report_type: str = "生态环境状况公报", limit: int = 15) -> dict:
    """读取指定类型环境质量报告的最新列表（公报多为 PDF 附件，可直接下载）。"""
    category = REPORT_TYPES.get(report_type)
    if not category:
        return {
            "report_type": report_type,
            "items": [],
            "note": f"未知报告类型：{report_type}；可用 list_quality_reports() 查看全部类型",
        }
    from .news import read_mee_list

    data = read_mee_list(fetcher, cache, category, limit=limit)
    data["report_type"] = report_type
    if report_type in PDF_DOMINANT:
        data["note"] = "该报告以 PDF 附件发布，列表中的 .pdf 链接可直接用 download_file 下载"
    return data
