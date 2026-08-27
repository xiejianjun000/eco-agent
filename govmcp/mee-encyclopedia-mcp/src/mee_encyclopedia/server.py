"""MEE Encyclopedia MCP 主入口：统一对外 MCP Server。

运行方式:
    python -m mee_encyclopedia.server
"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

from .core.cache import Cache
from .core.downloader import Downloader
from .core.fetcher import Fetcher
from .core.reader import Reader
from .core.utils import audit, get_download_base, load_config, setup_logging
from .domains import air, eia, interact, news, permit, policy, quality, radiation, search, solidwaste, standards, water
from .rag.store import RagStore
from .registry import list_domains

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG = load_config()
DOWNLOADS_DIR = get_download_base(CONFIG)
WORK_DIR = PROJECT_ROOT / "work"
WORK_DIR.mkdir(parents=True, exist_ok=True)

FETCHER = Fetcher(CONFIG)
CACHE = Cache(
    base_dir=WORK_DIR,
    ttl=int(CONFIG.get("cache", {}).get("ttl_seconds", 300)),
    ttl_slow=int(CONFIG.get("cache", {}).get("ttl_seconds_slow", 3600)),
    max_entries=int(CONFIG.get("cache", {}).get("max_entries", 512)),
)
READER = Reader(FETCHER)
DOWNLOADER = Downloader(
    FETCHER,
    base_dir=DOWNLOADS_DIR,
    max_size_mb=int(CONFIG.get("download", {}).get("max_size_mb", 200)),
)
RAG = RagStore(WORK_DIR / "rag")

mcp = FastMCP(
    "mee-encyclopedia-mcp",
    instructions=(
        "生态环境百科全书 MCP：实时获取生态环境部网站矩阵（主站+20直属单位+19派出机构+20业务系统）权威信息。"
        "支持读取（网页/环境质量/标准/政策/许可）与下载（标准PDF/数据导出/任意公开文件）。"
    ),
)


# ---------------- 读取工具族（核心能力 1） ----------------

@mcp.tool()
def read_web_page(url: str, max_chars: int = 8000) -> dict:
    """读取任意公开网页正文（来源 URL 需为生态环境部系统或用户明确指定）。"""
    audit("read_web_page", url)
    return READER.read_page(url, max_chars=max_chars)


@mcp.tool()
def list_web_links(url: str, limit: int = 50) -> dict:
    """列出网页中的公开链接，用于探索栏目结构。"""
    audit("list_web_links", url)
    return READER.list_links(url, limit=limit)


# ---------------- 环境质量实时数据 ----------------

@mcp.tool()
def read_air_quality(city: str) -> dict:
    """查询城市实时空气质量（AQI 与六项污染物）。"""
    audit("read_air_quality", city)
    return air.read_air_quality(FETCHER, CACHE, city)


@mcp.tool()
def read_air_forecast(region: str = "全国") -> dict:
    """读取空气质量预报信息。"""
    audit("read_air_forecast", region)
    return air.read_air_forecast(FETCHER, CACHE, region)


@mcp.tool()
def read_air_monthly(month: Optional[str] = None) -> dict:
    """读取全国环境空气质量状况月报（month 形如 202608）。"""
    audit("read_air_monthly", month or "latest")
    return air.read_air_monthly(FETCHER, CACHE, month)


@mcp.tool()
def read_surface_water(station: Optional[str] = None) -> dict:
    """读取国家地表水水质自动监测数据。"""
    audit("read_surface_water", station or "all")
    return water.read_surface_water(FETCHER, CACHE, station)


@mcp.tool()
def read_sea_water(region: Optional[str] = None) -> dict:
    """读取国家海水水质监测数据。"""
    audit("read_sea_water", region or "all")
    return water.read_sea_water(FETCHER, CACHE, region)


@mcp.tool()
def read_radiation_level(region: Optional[str] = None) -> dict:
    """读取全国空气吸收剂量率（辐射环境监测数据）。"""
    audit("read_radiation_level", region or "all")
    return radiation.read_radiation_level(FETCHER, CACHE, region)


# ---------------- 主站动态与政策标准 ----------------

@mcp.tool()
def list_mee_categories() -> dict:
    """列出全部可读栏目分组导览（要闻/政策/业务工作/环境质量/互动/曝光台/核安全局等 60+ 栏目）。"""
    return news.list_mee_categories()


@mcp.tool()
def read_mee_list(category: str = "要闻动态", limit: int = 20, keyword: Optional[str] = None) -> dict:
    """读取主站栏目最新列表：支持全部 60+ 栏目（要闻/政策文种/业务工作/环境质量报告/互动/曝光台/党建/专题/核安全局），可选 keyword 过滤标题。"""
    audit("read_mee_list", category)
    return news.read_mee_list(FETCHER, CACHE, category, limit=limit, keyword=keyword)


@mcp.tool()
def read_mee_article(url: str) -> dict:
    """读取主站文章正文（要闻/政策/公示详情）。"""
    audit("read_mee_article", url)
    return news.read_mee_article(FETCHER, CACHE, url)

@mcp.tool()
def list_policy_types() -> dict:
    """列出政策文种分类（部令/公告/文件/函/中央/国务院/行政审批/核安全局/解读）。"""
    return policy.list_policy_types()


@mcp.tool()
def read_policy_type(doc_type: str = "部令", limit: int = 15) -> dict:
    """按文种读取政策文件最新列表（如 部令/部公告/部文件/中央有关文件/政策解读）。"""
    audit("read_policy_type", doc_type)
    return policy.read_policy_type(FETCHER, CACHE, doc_type, limit=limit)


@mcp.tool()
def read_policy_interpretation(limit: int = 15) -> dict:
    """读取政策解读栏目最新列表（含一图读懂等解读文章）。"""
    audit("read_policy_interpretation", "政策解读")
    return policy.read_policy_type(FETCHER, CACHE, "政策解读", limit=limit)


@mcp.tool()
def list_quality_reports() -> dict:
    """列出全部可读环境质量报告类型（公报/年报/月报/预报）。"""
    return quality.list_quality_reports()


@mcp.tool()
def read_quality_report(report_type: str = "生态环境状况公报", limit: int = 15) -> dict:
    """读取环境质量报告最新列表：生态环境状况公报/统计年报/海洋公报/噪声报告/固废年报/移动源年报/地表水月报/海水浴场/空气质量状况/预报等。"""
    audit("read_quality_report", report_type)
    return quality.read_quality_report(FETCHER, CACHE, report_type, limit=limit)


@mcp.tool()
def list_interact_sections() -> dict:
    """列出互动交流与综合栏目导览（意见征集/留言选登/常见问题/曝光台/英文版/党建/专题）。"""
    return interact.list_interact_sections()


@mcp.tool()
def read_interact(section: str = "常见问题", limit: int = 15) -> dict:
    """读取互动交流栏目列表：意见征集-专题意见/意见征集-网上征集/留言选登/常见问题。"""
    audit("read_interact", section)
    return interact.read_interact(FETCHER, CACHE, section, limit=limit)


@mcp.tool()
def read_exposure(section: str = "通报", limit: int = 15) -> dict:
    """读取曝光台栏目列表：行政处理/执法信息/通报。"""
    audit("read_exposure", section)
    return interact.read_exposure(FETCHER, CACHE, section, limit=limit)


@mcp.tool()
def read_english_list(section: str = "新闻发布", limit: int = 15) -> dict:
    """读取生态环境部英文版栏目列表（About/Events/News/Resources）。"""
    audit("read_english_list", section)
    return interact.read_english_list(FETCHER, CACHE, section, limit=limit)


@mcp.tool()
def list_nnsa_sections() -> dict:
    """列出国家核安全局子站可读栏目（工作动态/政策文件/机构职能）。"""
    return radiation.list_nnsa_sections()


@mcp.tool()
def read_nnsa_list(section: str = "工作动态", limit: int = 15) -> dict:
    """读取国家核安全局子站栏目最新列表（工作动态/政策文件/机构职能）。"""
    audit("read_nnsa_list", section)
    return radiation.read_nnsa_list(FETCHER, CACHE, section, limit=limit)


@mcp.tool()
def search_site(keyword: str, limit: int = 15) -> dict:
    """生态环境部官网站内关键词搜索（只读公开搜索）。"""
    audit("search_site", keyword)
    return search.search_site(FETCHER, CACHE, keyword, limit=limit)


@mcp.tool()
def search_policy(keyword: str, limit: int = 10) -> dict:
    """按关键词检索政策文件。"""
    audit("search_policy", keyword)
    return policy.search_policy(FETCHER, CACHE, keyword, limit=limit)


@mcp.tool()
def read_policy(url: str) -> dict:
    """读取政策文件全文正文。"""
    audit("read_policy", url)
    return policy.read_policy(FETCHER, CACHE, url)


@mcp.tool()
def search_standard(keyword: str, limit: int = 10) -> dict:
    """按关键词检索生态环境标准（HJ/GB 目录）。"""
    audit("search_standard", keyword)
    return standards.search_standard(FETCHER, CACHE, keyword, limit=limit)


@mcp.tool()
def read_standard(standard_no: str) -> dict:
    """按编号读取标准信息（如 HJ 1294—2023）。"""
    audit("read_standard", standard_no)
    return standards.read_standard(FETCHER, CACHE, standard_no)


# ---------------- 业务系统查询（动态/需登录，返回入口与说明） ----------------

@mcp.tool()
def query_eia_credit(name: str) -> dict:
    """查询环评机构信用信息（信用平台为登录后动态系统，返回查询说明与入口）。"""
    audit("query_eia_credit", name)
    return eia.query_eia_credit(FETCHER, CACHE, name)


@mcp.tool()
def search_permit(company: str) -> dict:
    """查询企业排污许可证信息（业务系统需登录，返回查询说明与入口）。"""
    audit("search_permit", company)
    return permit.search_permit(FETCHER, CACHE, company)


@mcp.tool()
def search_waste_category(keyword: str) -> dict:
    """查询危险废物类别信息（名录/代码/危险特性）。"""
    audit("search_waste_category", keyword)
    return solidwaste.search_waste_category(FETCHER, CACHE, keyword)


# ---------------- 百科知识域（静态导览） ----------------

@mcp.tool()
def list_domains_meta() -> dict:
    """列出 15 大领域命名空间与可用工具。"""
    return {"domains": list_domains()}


@mcp.tool()
def list_agencies() -> dict:
    """列出生态环境部下属单位与派出机构网站矩阵（百科知识域）。"""
    agencies = CONFIG.get("sources", {}).get("agencies", {})
    rivers = CONFIG.get("sources", {}).get("river_bureaus", {})
    return {"直属单位": agencies, "流域海域局": rivers, "count": len(agencies) + len(rivers)}


@mcp.tool()
def list_river_bureaus() -> dict:
    """列出七大流域海域生态环境监督管理局入口。"""
    return water.list_river_bureaus()


@mcp.tool()
def list_nuclear_entrances() -> dict:
    """列出核与辐射安全核心系统入口。"""
    return radiation.list_nuclear_entrances()


@mcp.tool()
def list_eia_entrances() -> dict:
    """列出环评相关业务系统入口。"""
    return eia.list_eia_entrances()


@mcp.tool()
def list_waste_entrances() -> dict:
    """列出固废危废相关系统入口。"""
    return solidwaste.list_waste_entrances()


@mcp.tool()
def list_laws() -> dict:
    """列出生态环境法律法规体系。"""
    return policy.list_laws()


@mcp.tool()
def list_standard_categories() -> dict:
    """列出生态环境标准体系分类。"""
    return standards.list_standard_categories()


@mcp.tool()
def permit_guide() -> dict:
    """排污许可制度知识导览。"""
    return permit.permit_guide()


# ---------------- RAG 知识库 ----------------

@mcp.tool()
def rag_query(question: str, top_k: int = 5) -> dict:
    """在本地 RAG 知识库中检索政策/标准片段并返回带来源的候选答案。"""
    audit("rag_query", question)
    hits = RAG.search(question, top_k=top_k)
    return {"question": question, "hits": hits, "stats": RAG.stats()}


@mcp.tool()
def rag_ingest(doc_id: str, title: str, text: str, source: str = "") -> dict:
    """向 RAG 知识库注入一条文档（政策/标准/文章正文）。"""
    RAG.add(doc_id, title, text, source)
    return {"ingested": doc_id, "stats": RAG.stats()}


# ---------------- 下载工具族（核心能力 2） ----------------

@mcp.tool()
def download_file(url: str, save_dir: str = ".", filename: Optional[str] = None) -> dict:
    """下载公开 URL 文件到本地下载目录（仅 http/https，限制大小）。"""
    audit("download_file", url)
    return DOWNLOADER.download(url, save_dir=save_dir, filename=filename)


@mcp.tool()
def download_standard_pdf(standard_no: str, save_dir: str = "standards") -> dict:
    """按编号下载生态环境标准 PDF（在标准目录页检索并下载首个匹配附件）。"""
    audit("download_standard_pdf", standard_no)
    info = standards.read_standard(FETCHER, CACHE, standard_no)
    url = info.get("info", {}).get("url", "")
    if not url:
        return {"standard_no": standard_no, "success": False, "note": "未在目录页定位到该标准，请先 search_standard 获取 URL 后使用 download_file"}
    return DOWNLOADER.download(url, save_dir=save_dir)


@mcp.tool()
def export_mee_list(category: str = "要闻动态", save_dir: str = "exports", fmt: str = "json") -> dict:
    """导出主站栏目列表为 JSON/CSV 文件（数据下载能力）。"""
    audit("export_mee_list", f"{category}:{fmt}")
    data = news.read_mee_list(FETCHER, CACHE, category, limit=50)
    items = data.get("items", [])
    if fmt.lower() == "csv":
        lines = ["title,url"]
        for it in items:
            lines.append(f'"{it.get("title","")}","{it.get("url","")}"')
        content = "\n".join(lines)
        fname = f"mee_{category}_{len(items)}.csv"
    else:
        content = json.dumps(items, ensure_ascii=False, indent=2)
        fname = f"mee_{category}_{len(items)}.json"
    saved = DOWNLOADER.download_text(content, fname, save_dir=save_dir)
    return {"category": category, "count": len(items), **saved}


@mcp.tool()
def export_air_quality_csv(city: str, save_dir: str = "exports") -> dict:
    """导出城市实时空气质量数据为 CSV 文件。"""
    audit("export_air_quality_csv", city)
    data = air.read_air_quality(FETCHER, CACHE, city)
    rows = data.get("items", [])
    if not rows:
        return {"city": city, "success": False, "note": data.get("note", "无数据")}
    content = "city,aqi,pm25,pm10,so2,no2,co,o3,level,updated\n"
    for r in rows:
        content += ",".join(str(r.get(k, "")) for k in ["city", "aqi", "pm25", "pm10", "so2", "no2", "co", "o3", "level", "updated"]) + "\n"
    saved = DOWNLOADER.download_text(content, f"air_{city}_{len(rows)}.csv", save_dir=save_dir)
    return {"city": city, "rows": len(rows), **saved}


@mcp.tool()
def list_downloads(save_dir: str = ".") -> dict:
    """列出已下载文件（下载目录内容）。"""
    base = DOWNLOADS_DIR
    target = base
    if save_dir and save_dir != ".":
        from .core.utils import ensure_within
        target = ensure_within(base, Path(save_dir))
    files = []
    for p in sorted(target.rglob("*")):
        if p.is_file():
            files.append({"name": p.name, "path": str(p), "size": p.stat().st_size})
    return {"dir": str(target), "count": len(files), "files": files[:100]}


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="MEE Encyclopedia MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default="stdio",
        help="MCP 传输方式（默认 stdio，供 Claude Desktop/IDE 等客户端托管）",
    )
    args = parser.parse_args()
    setup_logging(os.getenv("MEE_LOG_LEVEL", CONFIG.get("logging", {}).get("level", "INFO")))
    logger.info("MEE Encyclopedia MCP 启动: transport=%s 领域=%d 下载目录=%s", args.transport, len(list_domains()), DOWNLOADS_DIR)
    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
