"""输出档位自动分档。

分档依据是「答错的代价」，不是问题长短——这是本模块唯一的设计前提，
测试首先守住这一点。
"""
from __future__ import annotations

import pytest

from agent_core.output_tier import NUMERIC_GUARD, Tier, classify, tier_sections


class TestTierByConsequence:
    """按责任后果分档，不按复杂度。"""

    @pytest.mark.parametrize("q", [
        "娄底市今天空气质量怎么样",
        "冷水江市有哪些国控站点",
        "什么是VOCs",
    ])
    def test_fact_query_is_brief(self, q):
        assert classify(q).tier == Tier.BRIEF

    @pytest.mark.parametrize("q", [
        "这个企业没验收就投产了，怎么处理",
        "为什么这两天PM2.5一直超标",
        "这算不算未批先建",
        "这两个标准有什么区别",
    ])
    def test_judgement_is_analysis(self, q):
        assert classify(q).tier == Tier.ANALYSIS

    @pytest.mark.parametrize("q", [
        "帮我起草一份责令改正违法行为决定书",
        "这个案子罚款幅度怎么定",
        "对这份案卷做一次评查",
        "这家企业的排污许可证变更要审核什么",
    ])
    def test_legal_output_is_formal(self, q):
        assert classify(q).tier == Tier.FORMAL

    def test_short_question_can_be_formal(self):
        """关键：短问题不等于低档位。答错要担责就得上档。"""
        d = classify("罚多少钱")
        assert d.tier == Tier.FORMAL, "涉裁量的短问题必须进正式档"

    def test_long_question_can_be_brief(self):
        """反向：长问题不必然高档位。"""
        q = "麻烦帮我查一下娄底市今天各个国控站点的实时空气质量数据分别是多少"
        assert classify(q).tier == Tier.BRIEF


class TestNumericGuard:
    """数值型答错代价最高——这是环境领域的特殊风险。"""

    @pytest.mark.parametrize("q", [
        "锅炉烟气排放限值是多少",
        "GB13223 里二氧化硫限值",
        "这个浓度 35 mg/m3 超标了吗",
        "罚款金额怎么算",
    ])
    def test_numeric_detected(self, q):
        assert classify(q).numeric is True

    def test_numeric_lifts_brief_to_analysis(self):
        """查限值看着像简单查询，但答错直接影响项目审批，必须上浮。"""
        d = classify("查一下锅炉烟气排放限值是多少")
        assert d.tier == Tier.ANALYSIS
        assert any("上浮" in r for r in d.reasons)

    def test_numeric_injects_guard(self):
        secs = tier_sections(classify("锅炉烟气排放限值是多少"))
        assert any(NUMERIC_GUARD in s for s in secs)

    def test_guard_demands_three_elements(self):
        """标准号 / 适用条件 / 基准氧含量，缺一不可——三者都得写进约束。"""
        for kw in ("标准号", "适用条件", "基准氧含量", "待确认"):
            assert kw in NUMERIC_GUARD

    def test_non_numeric_no_guard(self):
        secs = tier_sections(classify("什么是VOCs"))
        assert all(NUMERIC_GUARD not in s for s in secs)


class TestFailSafe:
    """判不准时必须偏保守——宁可多给依据。"""

    def test_unknown_defaults_to_analysis(self):
        d = classify("嗯")
        assert d.tier == Tier.ANALYSIS, "看不懂的问题不能给无出处的断言"

    def test_empty_input_safe(self):
        assert classify("").tier == Tier.BRIEF

    def test_attachment_lifts_tier(self):
        assert classify("看看这个", has_attachment=True).tier != Tier.BRIEF

    def test_reasons_always_explainable(self):
        """判定必须可解释，否则审计链上无法复核。"""
        for q in ["查空气质量", "怎么处理", "起草决定书", "xyz"]:
            assert classify(q).reasons, f"{q} 没有给出判定理由"


class TestSpecContent:
    """各档规格必须真的不同，否则分档没有意义。"""

    def test_specs_differ(self):
        specs = [tier_sections(classify(q))[0]
                 for q in ["娄底今天空气质量", "这算不算超标", "起草决定书"]]
        assert len(set(specs)) == 3, "三档规格必须互不相同"

    def test_brief_forbids_empty_headings(self):
        """简答档最容易被套模板套坏——必须明确禁止空标题。"""
        spec = tier_sections(classify("娄底今天空气质量"))[0]
        assert "空标题" in spec or "不需要" in spec

    def test_formal_requires_clause_level_citation(self):
        spec = tier_sections(classify("起草处罚决定书"))[0]
        assert "款" in spec and "项" in spec, "正式档必须要求条款项级引用"
        assert "生态环境法典" in spec, "旧法引用须标注法典对应条款"

    def test_analysis_puts_speculation_in_pending(self):
        spec = tier_sections(classify("为什么超标"))[0]
        assert "待确认" in spec and "推测" in spec


class TestEngineIntegration:
    """接入 PromptEngine：默认不改变行为，判定后才注入。"""

    def test_default_no_tier(self):
        from agent_core.prompt_engine import PromptEngine
        assert PromptEngine().tier is None, "未判定时不得注入档位规格"

    def test_apply_tier_injects_spec(self):
        from agent_core.prompt_engine import PromptEngine
        eng = PromptEngine()
        eng.apply_tier("这个案子罚款幅度怎么定")
        assert "输出规格 · 正式" in eng.build_system_prompt()

    def test_switch_writes_audit(self):
        """档位决策必须入链，否则事后无法复核判错。"""
        from agent_core.prompt_engine import PromptEngine
        eng = PromptEngine()
        before = len(eng.audit.tail(200))
        eng.apply_tier("起草一份处罚决定书")
        entries = eng.audit.tail(200)
        assert len(entries) > before
        assert any(e.get("source") == "output_tier" for e in entries)

    def test_audit_records_reason(self):
        """入链内容要含判定理由，不能只有档位名。"""
        from agent_core.prompt_engine import PromptEngine
        eng = PromptEngine()
        eng.apply_tier("这个案子罚款幅度怎么定")
        rec = [e for e in eng.audit.tail(50) if e.get("source") == "output_tier"]
        assert rec and "←" in rec[-1].get("content", "")

    def test_safety_layer_still_first(self):
        """追加式改造：安全层位置不得被档位规格挤动。"""
        from agent_core.prompt_engine import PromptEngine, SAFETY_LAYER
        eng = PromptEngine()
        eng.apply_tier("起草处罚决定书")
        p = eng.build_system_prompt()
        assert p.index(SAFETY_LAYER[:40]) < p.index("输出规格")


class TestRealDomainQuestions:
    """真实领域问法回归。

    语料来源：ecoskills/eia-router/SKILL.md 的意图信号词，
    以及从 ecoskills/ 挖出的行业术语（未批先建/重大变动/稀释排放/
    自动监测/台账/执行报告/重点管理…）。

    这批问句一次性暴露了 5 个漏判——都是我自己编测试用例编不出来的，
    因为行业惯用语（「如何处罚」而非「行政处罚」、「台账保存几年」）
    不在通用直觉里。故固化为回归测试。
    """

    @pytest.mark.parametrize("q", [
        "执行报告多久提交一次",
        "台账要保存几年",
        "排污许可证有效期几年",
    ])
    def test_deadline_query_is_brief(self, q):
        """期限/频次是查规定，不是判定。原正则漏了「多久/几年」。"""
        assert classify(q).tier == Tier.BRIEF

    @pytest.mark.parametrize("q", [
        "什么情况下需要重新报批环评",
        "这个项目要不要做环评",
        "排污登记和排污许可有什么区别",
        "属于重点管理还是简化管理",
        "这算重大变动吗",
        "稀释排放怎么认定",
        "旁路偷排怎么查",
        "这算不算未批先建",
        "这个企业没验收就投产了，怎么处理",
    ])
    def test_determination_is_analysis(self, q):
        """定性、口径、处置路径 → 分析档。

        注意「这算不算未批先建」和「没验收就投产怎么处理」：
        问的是定性与处置路径，回答不进法律文件，不该升到正式档。
        扩词表时一度把它们误升，这两条专门守住边界。
        """
        assert classify(q).tier == Tier.ANALYSIS

    @pytest.mark.parametrize("q", [
        "未批先建如何处罚",
        "无证排污怎么处罚",
        "超标排放的处罚依据是什么",
        "自动监测数据能不能作为处罚依据",
    ])
    def test_penalty_question_is_formal(self, q):
        """口语化处罚问法必须进正式档。

        「未批先建如何处罚」是 eia-router 明列的日常问句，
        但原正则只认「行政处罚/处罚决定」，把它判成了分析档——
        少给条款级依据和裁量说明，这是会出事的漏判。

        「自动监测数据能不能作为处罚依据」问的是证据能力，
        答错会导致证据被排除，同样按正式档处理。
        """
        assert classify(q).tier == Tier.FORMAL

    def test_violation_word_alone_not_formal(self):
        """违法情形词单独出现不足以升档——避免过度分类。"""
        assert classify("未批先建是什么意思").tier != Tier.FORMAL

    def test_compound_question_keeps_numeric_guard(self):
        """eia-router 举的复合问句：手续 + 限值 + 口径。

        只要含限值就必须挂数值守卫，不因为问题混杂而丢掉。
        """
        d = classify("这个火电项目要办什么手续、氮氧化物限值多少、有没有官方口径")
        assert d.numeric is True
        assert NUMERIC_GUARD in "".join(tier_sections(d))
