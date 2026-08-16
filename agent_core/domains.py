#!/usr/bin/env python3
"""
agent_core/domains.py — 生态环境全要素知识域体系

Eco Agent 的定位不是单一案卷评查工具，而是全生态环境垂直系统智能体：
既懂法律法规、又懂技术标准、又懂数据分析、也懂各个环境要素。

本模块是知识域标签的单一权威源（技能分类 / 记忆树 domain 标签 / SOUL 引用）。
"""

from __future__ import annotations

# 环境要素域（介质）
ELEMENT_DOMAINS = {
    "atmosphere": {"label": "大气", "keywords": ["大气", "废气", "VOCs", "挥发性有机物", "扬尘", "机动车", "臭氧"]},
    "water": {"label": "水", "keywords": ["水污染", "废水", "地表水", "地下水", "饮用水", "入河排污口"]},
    "soil": {"label": "土壤", "keywords": ["土壤", "建设用地", "农用地", "地下水污染"]},
    "solid_waste": {"label": "固废", "keywords": ["固废", "工业固废", "生活垃圾", "建筑垃圾", "污泥"]},
    "noise": {"label": "噪声", "keywords": ["噪声", "声环境", "建筑施工噪声", "工业噪声"]},
    "radiation": {"label": "辐射", "keywords": ["辐射", "核技术", "电磁", "放射源"]},
    "ecology": {"label": "生态", "keywords": ["生态", "自然保护地", "生物多样性", "生态红线", "湿地"]},
    "carbon": {"label": "碳", "keywords": ["碳", "碳排放", "碳交易", "CCER", "碳足迹", "温室气体"]},
}

# 监管/专业域
REGULATORY_DOMAINS = {
    "eia": {"label": "环评", "keywords": ["环评", "环境影响评价", "未批先建", "三同时"]},
    "permit": {"label": "排污许可", "keywords": ["排污许可", "排污许可证", "证后监管", "许可排放"]},
    "cems": {"label": "在线监测", "keywords": ["CEMS", "在线监测", "自动监测", "数据造假", "运维"]},
    "hazmat": {"label": "危废/危化", "keywords": ["危废", "危险废物", "危化品", "化学品"]},
    "emergency": {"label": "应急", "keywords": ["应急", "突发环境事件", "应急预案", "风险管控"]},
    "total": {"label": "总量减排", "keywords": ["总量", "减排", "排污权", "清洁生产"]},
    "mobile": {"label": "移动源", "keywords": ["移动源", "机动车", "非道路机械", "船舶"]},
}

# 能力域（Eco Agent 的四大支柱）
CAPABILITY_DOMAINS = {
    "law": {"label": "法律法规", "keywords": ["法条", "法规", "处罚幅度", "裁量", "法典", "行政复议", "诉讼"]},
    "standards": {"label": "技术标准", "keywords": ["标准", "HJ", "GB", "排放限值", "监测规范", "采样", "化验"]},
    "data": {"label": "数据分析", "keywords": ["数据", "统计分析", "趋势", "超标", "比对", "CEMS 数据", "研判"]},
    "enforcement": {"label": "执法办案", "keywords": ["执法", "立案", "调查", "笔录", "告知", "决定", "文书", "移送"]},
    "inspection": {"label": "督察", "keywords": ["督察", "帮扶", "信号", "整改", "回头看"]},
    "review": {"label": "案卷评查", "keywords": ["评查", "案卷", "一票否决", "合法性", "规范性"]},
}

ALL_DOMAINS: dict[str, dict] = {**ELEMENT_DOMAINS, **REGULATORY_DOMAINS, **CAPABILITY_DOMAINS}


def classify_domain(text: str) -> list[str]:
    """按关键词把一段文本归入知识域，返回匹配的域 id 列表（按命中数排序）。"""
    scores: dict[str, int] = {}
    t = str(text)
    for domain_id, spec in ALL_DOMAINS.items():
        hits = sum(1 for kw in spec["keywords"] if kw in t)
        if hits:
            scores[domain_id] = hits
    return [d for d, _ in sorted(scores.items(), key=lambda kv: -kv[1])]


def domain_labels(domain_ids: list[str]) -> list[str]:
    return [ALL_DOMAINS[d]["label"] for d in domain_ids if d in ALL_DOMAINS]


def domain_overview() -> dict:
    """全要素知识域总览（SOUL/文档引用）。"""
    return {
        "element_domains": {k: v["label"] for k, v in ELEMENT_DOMAINS.items()},
        "regulatory_domains": {k: v["label"] for k, v in REGULATORY_DOMAINS.items()},
        "capability_domains": {k: v["label"] for k, v in CAPABILITY_DOMAINS.items()},
        "total_domains": len(ALL_DOMAINS),
    }
