#!/usr/bin/env python3
"""
law_enforcement.py — 执法领域专家团（平移自 agent_core/role_swarm.py 三角色 DAG）

角色与 RoleSwarm.ROLES 完全一致，仅声明式重写；运行器 ExpertTeam 复刻了
RoleSwarm 的并行 DAG、成本分级、审计链、法条自动核验、贡献段+总管合成等成熟机制，
因此本 spec 与既有 RoleSwarm 行为等价（见 tests/modules/test_expert_team.py）。

后续可将 server/api/chat.py 中 RoleSwarm 的接线改为 get_team("law_enforcement")，
实现「写死的三角色」→「注册表驱动」的收敛（本 spec 即为单一真源）。
"""

from agent_core.expert_team import RoleSpec, TeamSpec

_LAW_SYNTH_BRIEF = (
    "你是执法任务总管。三位专家（巡查/法规/文书）已分别给出产出。"
    "请仲裁合成最终输出：去重、纠偏（以法规核验为准）、补漏，"
    "给出一份可执行的检查清单。引用法条保留具体条款号。"
    "格式硬要求：结论先行、要点式，除条文原文引用外总长不超过 300 字，"
    "能用表格/列表绝不用段落，禁止输出编排头（如'三角色协作/贡献段'）。"
    "禁止在最终输出中出现编排内部词汇——'三方/三角色/三位专家/各角色/"
    "巡查Agent/法规Agent/文书Agent/仲裁'一律不得出现，以单人视角直接陈述结论。"
    "用中文，结构清晰。"
)

LAW_SPEC = TeamSpec(
    id="law_enforcement",
    name="执法领域专家团",
    domain="law_enforcement",
    description="三角色执法协作：巡查（现场取证）→ 法规（法条核验）→ 文书（清单生成）→ 总管合成。",
    roles=[
        RoleSpec(
            key="patrol", name="巡查Agent", phase="inspection", soul="searcher",
            brief=("你是现场巡查专家。针对任务给出现场检查要点：检查对象/部位、"
                   "取证规范（照片、笔录、监测数据、台账）、违法线索初步判断。证据意识优先。"),
            max_tokens=700, tier="role",
        ),
        RoleSpec(
            key="law", name="法规Agent", phase="review", soul="reviewer",
            brief=("你是法规核验专家。针对任务核验适用法律法规：给出真实现行有效的法规名称与具体条款号，"
                   "说明违法构成与裁量要点；不确定的法条明确标注不确定，禁止编造。"),
            max_tokens=700, tier="role", verify_articles=True,
        ),
        RoleSpec(
            key="doc", name="文书Agent", phase="documentation", soul="writer",
            brief=("你是执法文书专家。根据巡查要点与法规核验结果，生成检查记录框架与巡查清单："
                   "要素完整（当事人/事实/证据/法律依据/裁量说明），用语规范。"),
            max_tokens=900, tier="role", depends_on=["patrol", "law"],
        ),
    ],
    synth_brief=_LAW_SYNTH_BRIEF,
    synth_tier="synth",
    complexity_hints=[
        "全套", "全面检查", "综合执法", "检查方案", "专项行动", "排查", "一案双查",
        "检查清单", "现场检查并", "立案", "案卷", "联合检查", "帮扶检查",
    ],
    eval_rubric=[
        "巡查要点覆盖检查对象/部位/取证规范",
        "法规核验给出具体条款号且经工具校验存在",
        "裁量要点与违法构成说明准确",
        "文书要素完整（当事人/事实/证据/法律依据/裁量说明）",
        "最终合成结论先行、去重纠偏、无编造",
    ],
)
