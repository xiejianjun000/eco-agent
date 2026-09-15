#!/usr/bin/env python3
"""
air_source.py — 大气溯源领域专家团（10-Agent：9 专家 + 1 总管合成）

拓扑（由 depends_on 推导 wave，同 wave 并行）：
  wave0  数据接入
  wave1  污染指纹 ∥ 传输轨迹 ∥ 源解析 ∥ 气象耦合 ∥ 空间格局 ∥ 历史同比
  wave2  成因研判（依赖 wave1 六方）
  wave3  管控建议（依赖成因研判）
  合成   报告合成（总管，synth tier）

复用 eco-Agent 既有真实数据能力：cnemc（CNEMC 国控站逐小时 AQI/六参）、
eco-Meteo-MCP（后向轨迹/源解析/气象）。各角色 brief 写入真实源解析方法论，
契合「用真数据说话」「垂直 Agent 胜负手在领域脏活」的方法论（docs/vertical-agent-research）。
"""

from agent_core.expert_team import RoleSpec, TeamSpec

_AIR_SYNTH_BRIEF = (
    "你是大气溯源研判总管。成因研判与管控建议已分别给出。"
    "请综合为一份结构化溯源研判报告：结论先行（首要污染物、污染类型、主导成因、置信度），"
    "再列数据支撑、源贡献率、气象条件、空间特征、历史对比，最后给管控建议清单。"
    "能用表格/列表绝不用段落；除数据/条文原文外总长不超过 400 字；"
    "以单人视角直接陈述，禁止出现'各方/各专家/仲裁/合成/总管'等编排内部词汇。"
    "用中文，结构清晰。"
)

AIR_SOURCE_SPEC = TeamSpec(
    id="air_source",
    name="大气溯源专家团",
    domain="air_quality",
    description="10-Agent 大气溯源研判：数据接入→（指纹/轨迹/源解析/气象/空间/历史）并行→成因→管控→报告合成。",
    roles=[
        RoleSpec(
            key="data_ingest", name="数据接入Agent",
            brief=("你是大气溯源「数据接入」专家。根据任务给定的城市/站点与时间范围，接入真实监测数据："
                   "CNEMC 国控站点逐小时 AQI、PM2.5、PM10、O3、NO2、SO2、CO，以及同期气象要素"
                   "（温度、相对湿度、风速、风向、边界层高度、降水量）。明确列出数据来源、时间覆盖与站点清单；"
                   "数据缺失如实标注，禁止编造。输出：站点清单 / 时间范围 / 六参浓度 / 气象要素。"),
            max_tokens=800, tier="role",
            tools=["query_air_quality(cnemc)", "eco-Meteo-MCP 气象"],
        ),
        RoleSpec(
            key="fingerprint", name="污染指纹Agent",
            brief=("你是大气溯源「污染指纹」专家。基于接入的浓度数据，用污染物比值判定首要污染物与污染类型："
                   "NO2/SO2 高→燃煤/机动车；PM2.5/PM10>0.6→细颗粒二次转化；O3 主导→光化学污染；"
                   "粗颗粒高→扬尘。给出首要污染物、污染类型归类（扬尘型/燃煤型/机动车型/工业型/二次转化型）"
                   "及判据。标注不确定项。"),
            max_tokens=700, tier="role",
            tools=["query_air_quality(cnemc)"], depends_on=["data_ingest"],
        ),
        RoleSpec(
            key="trajectory", name="传输轨迹Agent",
            brief=("你是大气溯源「传输轨迹」专家。基于气象与风场，分析区域传输贡献：后向轨迹聚类（HYSPLIT 思路）"
                   "+ 潜在源区贡献（PSCF/CWT）。判断外来传输占比与主要来向扇区；静稳（低风速）时提示本地累积主导。"
                   "输出：主导来向、传输占比量级、潜在源区。"),
            max_tokens=700, tier="role",
            tools=["eco-Meteo-MCP 后向轨迹/PSCF"], depends_on=["data_ingest"],
        ),
        RoleSpec(
            key="source_apportionment", name="源解析Agent",
            brief=("你是大气溯源「源解析」专家。用受体模型思路（PMF/CMB）结合本地排放清单与源成分谱，"
                   "估算主要源类贡献率：工业企业、道路/非道路移动源、扬尘（施工/裸土/道路）、燃煤、"
                   "生物质燃烧、二次硫酸盐/硝酸盐/铵盐。给出各源类贡献率量级排序与依据；区分一次源与二次转化。"),
            max_tokens=800, tier="role",
            tools=["eco-Meteo-MCP 源解析", "本地排放清单"], depends_on=["data_ingest"],
        ),
        RoleSpec(
            key="meteo_coupling", name="气象耦合Agent",
            brief=("你是大气溯源「气象耦合」专家。分析气象条件对污染累积的贡献：静稳度（低风速、弱扰动）、"
                   "逆温（贴地/高空逆温层）、高湿（促进二次转化与吸湿增长）、边界层高度压低、降水清除缺失。"
                   "给出气象条件是「利于累积」还是「利于扩散」，及关键指标。"),
            max_tokens=700, tier="role",
            tools=["eco-Meteo-MCP 气象"], depends_on=["data_ingest"],
        ),
        RoleSpec(
            key="spatial", name="空间格局Agent",
            brief=("你是大气溯源「空间格局」专家。比较目标站点与周边站点的同期浓度梯度与相关性："
                   "高相关性→区域传输信号；本地高、周边低→本地源主导；空间异质性→局地排放。"
                   "输出空间梯度特征与本地/区域信号判断。"),
            max_tokens=700, tier="role",
            tools=["query_air_quality(cnemc) 多站"], depends_on=["data_ingest"],
        ),
        RoleSpec(
            key="historical", name="历史同比Agent",
            brief=("你是大气溯源「历史同比」专家。回溯近 N 年同时段（同期）污染水平：同比/环比变化、"
                   "历史相似污染个例、是否异常偏高。区分「季节性常态」与「异常污染过程」。"
                   "输出：同期位次、相似个例、是否异常。"),
            max_tokens=700, tier="role",
            tools=["历史数据检索"], depends_on=["data_ingest"],
        ),
        RoleSpec(
            key="causation", name="成因研判Agent", tier="synth",
            brief=("你是大气溯源「成因研判」专家。综合污染指纹、传输轨迹、源解析、气象耦合、空间格局、"
                   "历史同比六方结论，判定主导成因：本地累积 vs 区域传输 vs 二次转化，"
                   "给出各成因的相对权重与置信度（高/中/低）。结论先行，禁止编造数据。"),
            max_tokens=900,
            depends_on=["fingerprint", "trajectory", "source_apportionment",
                        "meteo_coupling", "spatial", "historical"],
        ),
        RoleSpec(
            key="control_advice", name="管控建议Agent",
            brief=("你是大气溯源「管控建议」专家。针对主导成因给出可操作的分时段应急管控建议："
                   "本地累积→强化扬尘管控与工业错峰；区域传输→区域协同减排；二次转化→VOCs/NOx 协同管控；"
                   "机动车→移动源管控。参考重污染天气应急预案分级（黄/橙/红）。建议须具体、可执行。"),
            max_tokens=800, tier="role", depends_on=["causation"],
        ),
    ],
    synth_brief=_AIR_SYNTH_BRIEF,
    synth_tier="synth",
    complexity_hints=[
        "溯源", "污染成因", "污染研判", "源解析", "重污染", "空气质量分析",
        "臭氧", "PM2.5", "空气质量预报", "传输", "大气污染过程",
    ],
    eval_rubric=[
        "首要污染物与污染类型判定有据（浓度比值）",
        "传输占比与来向扇区有轨迹/风场依据",
        "源贡献率量级合理且与本地排放清单一致",
        "气象条件（静稳/逆温/高湿）与污染累积方向一致",
        "成因研判给出主导成因 + 相对权重 + 置信度",
        "管控建议针对主导成因、具体可执行",
    ],
)
