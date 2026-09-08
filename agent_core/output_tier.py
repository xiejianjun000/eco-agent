#!/usr/bin/env python3
"""
output_tier.py — 按「回答要担的责任」自动分档输出规格

为什么不按问题复杂度分：
    简单问题也可能后果严重。「这个企业罚多少钱」很短，但答错会导致行政复议；
    「帮我梳理一下最近的空气质量趋势」很长，答错了改一下就行。
    分档依据必须是**答错的代价**，不是问题的长短或工具调用次数。

三档：
    brief     查数据/查事实。答错可更正。要求：结论 + 出处。
    analysis  判定/分析/建议。答错会误导决策。要求：结论 + 依据 + 方法 + 待确认。
    formal    文书/审查/裁量。答错进入法律文件。要求：完整六模块 + 逐项溯源。

设计约束（来自 eco 宪法）：
    纪律 4 零幻觉  —— 不确定的必须标「待确认」，所以每档都保留该位置
    纪律 3 可追溯  —— formal 档逐项给原文指针
    D12 反幻觉 ≥95% —— 数值型答案强制附标准号/适用条件（见 NUMERIC_GUARD）

判定必须可解释：classify() 返回命中的具体理由，写入 SM3 审计链。
不做黑盒打分——审计链上出现一个没有理由的档位切换，等于无法复核。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

__all__ = ["Tier", "TierDecision", "classify", "tier_sections", "NUMERIC_GUARD"]


class Tier:
    BRIEF = "brief"
    ANALYSIS = "analysis"
    FORMAL = "formal"


ORDER = {Tier.BRIEF: 0, Tier.ANALYSIS: 1, Tier.FORMAL: 2}
NAMES = {Tier.BRIEF: "简答", Tier.ANALYSIS: "分析", Tier.FORMAL: "正式"}


@dataclass
class TierDecision:
    tier: str
    reasons: list[str] = field(default_factory=list)
    numeric: bool = False

    @property
    def name(self) -> str:
        return NAMES.get(self.tier, self.tier)

    def summary(self) -> str:
        r = "；".join(self.reasons) if self.reasons else "无特征命中，按默认档"
        return f"{self.tier}({self.name}) ← {r}"


# ── formal：进入法律文件或产生法律后果 ─────────────────────────
# 这些词出现即意味着输出会被引用、存档或作为处理依据
_FORMAL = [
    (r"(行政处罚|处罚决定|立案|结案|听证|告知书|决定书|责令改正|查封|扣押|按日计罚|移送)", "涉行政处罚程序"),
    (r"(裁量|罚.{0,4}(多少|幅度|区间)|罚款.{0,6}(标准|金额|数额)|从重|从轻|减轻|不予处罚)", "涉裁量幅度"),
    (r"(案卷|评查|文书|笔录|询问笔录|现场检查记录|勘察)", "涉执法文书"),
    (r"(环评|环境影响评价).{0,8}(审批|批复|审查|受理|退回)", "涉环评审批"),
    (r"(排污许可证).{0,8}(审核|核发|变更|注销|延续|检查)", "涉排污许可核发"),
    (r"(验收|竣工验收).{0,6}(意见|结论|审查)", "涉验收结论"),
    (r"(督察|问责|整改方案|销号)", "涉督察整改"),
    (r"(起草|出具|生成|写).{0,8}(报告|意见|文书|函|通知|方案)", "要求出具正式文件"),
]

# ── analysis：需要判断、推理、给建议 ────────────────────────────
_ANALYSIS = [
    (r"(是否|算不算|属于|构成|够不够|能不能|该不该|要不要)", "要求作出判定"),
    (r"(为什么|原因|怎么回事|如何解释|分析)", "要求因果分析"),
    (r"(怎么办|如何处理|怎么处理|建议|方案|措施|对策)", "要求给出处置建议"),
    (r"(超标|违法|违规|不达标|异常|超排|偷排|漏报)", "涉合规判定"),
    (r"(对比|比较|差异|区别|哪个更)", "要求比较"),
    (r"(风险|影响|后果|危害)", "要求风险研判"),
    (r"(适用|依据什么|按哪条|哪个标准)", "要求法条/标准适用"),
]

# ── brief：查事实、查数据 ───────────────────────────────────────
_BRIEF = [
    (r"(多少|几个|数量|总数|列出|有哪些|查询|查[一下过看]?|看一下|告诉我)", "事实型查询"),
    (r"(是什么|什么是|叫什么|全称|简称)", "定义型查询"),
    (r"(今天|昨天|实时|当前|最新).{0,10}(空气|水质|AQI|PM|噪声|数据)", "实时数据查询"),
]

# ── 数值型：答错代价最高，无论哪一档都要溯源 ───────────────────
_NUMERIC = [
    r"(限值|标准值|浓度限值|排放标准|基准|阈值)",
    r"(mg/m3|mg/m³|mg/L|μg/m3|µg/m³|ug/m3|吨/年|t/a)",
    r"(超标|达标).{0,6}(倍数|多少|判定)",
    r"(罚款|处罚).{0,6}(金额|数额|多少|幅度)",
    r"(基准氧含量|折算|标态|参照标准)",
    r"GB\s?\d{4,5}",
]

NUMERIC_GUARD = (
    "【数值溯源强制要求】本次回答涉及限值/标准/裁量金额等数值。"
    "任何具体数字必须同时给出：①标准号或法条（精确到条款项）②适用条件"
    "（行业/规模/时段/区域/新老源）③如涉浓度须注明基准氧含量或折算方式。"
    "三项缺任意一项，必须把该数字标注为「待确认」并说明缺什么，不得直接给出。"
    "国家标准与地方标准并存时，先给国标再给地标，并说明从严原则。"
)


def _hit(text: str, rules: list[tuple[str, str]]) -> list[str]:
    out = []
    for pat, why in rules:
        if re.search(pat, text, re.I):
            out.append(why)
    return out


def classify(message: str, *, has_attachment: bool = False) -> TierDecision:
    """按责任后果判定输出档位。判定理由必须可解释，用于写入审计链。"""
    text = (message or "").strip()
    if not text:
        return TierDecision(Tier.BRIEF, ["空输入"])

    formal = _hit(text, _FORMAL)
    analysis = _hit(text, _ANALYSIS)
    brief = _hit(text, _BRIEF)
    numeric = any(re.search(p, text, re.I) for p in _NUMERIC)

    reasons: list[str] = []
    if formal:
        tier = Tier.FORMAL
        reasons = formal[:3]
    elif analysis:
        tier = Tier.ANALYSIS
        reasons = analysis[:3]
    elif brief:
        tier = Tier.BRIEF
        reasons = brief[:2]
    else:
        # 无明确特征：默认 analysis 而非 brief。
        # 宁可多给依据，也不要在看不懂问题时给一个没有出处的断言。
        tier = Tier.ANALYSIS
        reasons = ["未命中明确特征，保守取分析档"]

    # 数值型上浮：查限值看似简单，但答错直接影响项目审批
    if numeric and ORDER[tier] < ORDER[Tier.ANALYSIS]:
        tier = Tier.ANALYSIS
        reasons.append("含数值型问题，上浮至分析档")

    # 带附件通常意味着要审材料，不是随口一问
    if has_attachment and ORDER[tier] < ORDER[Tier.ANALYSIS]:
        tier = Tier.ANALYSIS
        reasons.append("带附件，按材料审查处理")

    return TierDecision(tier, reasons, numeric)


# ── 各档输出规格 ────────────────────────────────────────────────
_BRIEF_SPEC = (
    "【输出规格 · 简答】直接给结论，不要铺垫。"
    "结论后用一行说明数据来源（工具名/站点/时间）。"
    "不要输出「依据/方法/风险」等空标题——本档不需要它们。"
    "如果查不到，直接说查不到以及原因，不要用推测填充。"
)

_ANALYSIS_SPEC = (
    "【输出规格 · 分析】按此顺序，标题用中文，没有内容的模块直接省略：\n"
    "① 结论：先给判断，一到两句说清。\n"
    "② 依据：每条依据标出处（法条精确到条款项，数据标站点与时间）。\n"
    "③ 方法：说明判定口径（用了哪个标准、怎么比对、有无折算）。\n"
    "④ 待确认：把不确定的、缺数据的、需要现场核实的单独列出。\n"
    "禁止把推测写进「结论」或「依据」——推测一律进「待确认」。"
)

_FORMAL_SPEC = (
    "【输出规格 · 正式】本次输出可能进入法律文件或作为处理依据，按此结构完整给出：\n"
    "① 结论：明确的定性或处理意见。\n"
    "② 事实与证据：逐项列明，每项标证据来源；缺失的证据必须写明「缺」。\n"
    "③ 法律依据：精确到法律名称 + 条 + 款 + 项；引用旧法须同时标注"
    "《生态环境法典》（2026-08-15 施行）对应条款。\n"
    "④ 裁量说明：如涉处罚，列出裁量阶次、基准、从重从轻情节及其依据。\n"
    "⑤ 程序要点：立案/告知/听证/送达等程序节点的合规提示。\n"
    "⑥ 待确认与风险：证据不足项、法条竞合项、可能的复议争点。\n"
    "硬性要求：③ 不得出现没有条款号的法条引用；② 不得出现没有来源的事实认定。"
)

_SPECS = {Tier.BRIEF: _BRIEF_SPEC, Tier.ANALYSIS: _ANALYSIS_SPEC, Tier.FORMAL: _FORMAL_SPEC}


def tier_sections(decision: TierDecision) -> list[str]:
    """把档位决策展开成可注入的提示词片段（追加式，不改安全层）。"""
    out = [_SPECS[decision.tier]]
    if decision.numeric:
        out.append(NUMERIC_GUARD)
    return out
