"""领域注册表：15 大领域命名空间与工具归属元数据。"""
from __future__ import annotations

DOMAIN_REGISTRY = {
    "air": {
        "name": "大气环境",
        "tools": ["read_air_quality", "read_air_forecast", "read_air_monthly", "export_air_quality_csv"],
    },
    "water": {
        "name": "水环境",
        "tools": ["read_surface_water", "read_sea_water", "list_river_bureaus"],
    },
    "soil": {
        "name": "土壤与地下水",
        "tools": ["read_mee_list(土壤生态环境)", "read_quality_report(固废年报)"],
    },
    "solidwaste": {
        "name": "固废危废",
        "tools": ["search_waste_category", "list_waste_entrances"],
    },
    "noise": {
        "name": "噪声振动",
        "tools": ["read_quality_report(噪声污染防治报告)"],
    },
    "radiation": {
        "name": "辐射与核安全",
        "tools": ["read_radiation_level", "list_nuclear_entrances", "read_nnsa_list", "list_nnsa_sections"],
    },
    "ecology": {
        "name": "生态保护",
        "tools": ["read_mee_list(自然生态保护)"],
    },
    "eia": {
        "name": "环评管理",
        "tools": ["query_eia_credit", "list_eia_entrances"],
    },
    "regulation": {
        "name": "排污许可与执法",
        "tools": ["search_permit", "permit_guide", "read_exposure"],
    },
    "climate": {
        "name": "气候变化",
        "tools": ["read_mee_list(应对气候变化)"],
    },
    "intl": {
        "name": "国际合作",
        "tools": ["read_mee_list(国际交流合作)", "read_english_list"],
    },
    "sciedu": {
        "name": "科技标准",
        "tools": ["search_standard", "read_standard", "list_standard_categories"],
    },
    "news": {
        "name": "要闻公示",
        "tools": ["read_mee_list", "read_mee_article", "export_mee_list", "list_mee_categories", "search_site"],
    },
    "quality": {
        "name": "环境质量报告",
        "tools": ["read_quality_report", "list_quality_reports"],
    },
    "interact": {
        "name": "互动交流",
        "tools": ["read_interact", "read_exposure", "read_english_list", "list_interact_sections"],
    },
}


def list_domains() -> list[dict]:
    return [{"code": k, "name": v["name"], "tools": v["tools"]} for k, v in DOMAIN_REGISTRY.items()]
