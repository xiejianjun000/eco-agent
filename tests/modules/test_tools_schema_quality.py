"""工具 schema 质量扫描：零参数工具清零、无通稿描述、参数描述完整、源表无重名。"""
from collections import Counter

from agent_core import tools_registry as tr


class TestToolSchemaQuality:
    def test_no_zero_param_tools(self):
        zero = [t["function"]["name"] for t in tr.ALL_TOOL_DEFS
                if not t["function"].get("parameters", {}).get("properties")]
        assert zero == [], f"仍有零参数工具: {zero}"

    def test_no_template_descriptions(self):
        descs = [t["function"]["name"] for t in tr.get_tools()
                 for _ in [t["function"].get("description", "")]]
        cnt = Counter(t["function"].get("description", "") for t in tr.get_tools())
        shared = {d: n for d, n in cnt.items() if n > 2}
        assert shared == {}, f"同一描述被 >2 个工具共用: {shared}"
        # 白名单瘦身（2026-08-16）：LLM 可见表仅真实实现（内置5+外部注册）
        assert len(descs) >= 5

    def test_all_params_have_description(self):
        bad = [(t["function"]["name"], p)
               for t in tr.get_tools()
               for p, s in t["function"].get("parameters", {}).get("properties", {}).items()
               if not s.get("description")]
        assert bad == [], f"参数缺少 description: {bad}"

    def test_no_duplicate_names_in_source(self):
        names = [t["function"]["name"] for t in tr.ALL_TOOL_DEFS]
        dups = {k: v for k, v in Counter(names).items() if v > 1}
        assert dups == {}, f"源表存在重名定义: {dups}"

    def test_no_duplicate_export_runtime(self):
        # 运行时不再出现重名去重告警
        assert tr.get_duplicate_tools() == []

    def test_zero_param_tools_got_semantic_params(self):
        by_name = {t["function"]["name"]: t["function"] for t in tr.ALL_TOOL_DEFS}
        fn = by_name["apply_business_license"]
        props = fn["parameters"]["properties"]
        assert "company_name" in props and "legal_person" in props
        assert "company_name" in fn["parameters"]["required"]
        assert props["company_name"]["description"]
        # 贴合语义：碳核查工具要求企业+年度
        fn2 = by_name["apply_carbon_verification"]
        assert set(fn2["parameters"]["required"]) == {"company_name", "year"}
