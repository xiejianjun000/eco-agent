#!/usr/bin/env python3
"""落盘守卫测试：LLM 不可用占位串绝不能被当正常回答/文档落盘。

真实事故：RoleSwarm 三角色与总管合成都拿到 "[LLM unavailable: all backends
failed]"，被 truthy 判断当正常回复，用户要「生成 md 文档并保存」只收到 38 字
错误，既没回落单循环也没产物；系统兜底若不加守卫还会把错误串存成假文档。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from server.api.chat import _is_llm_unavailable_text, _SAVE_REQUEST_RE  # noqa: E402


class TestIsUnavailable:
    def test_placeholders(self):
        for s in [
            "[LLM unavailable: all backends failed]",
            " [LLM unavailable: disabled by ECO_LLM_DISABLE] ",
            "[LLM unavailable: Run: eco setup]",
            "[eco-server] LLM 调用失败: HTTP 502",
        ]:
            assert _is_llm_unavailable_text(s) is True

    def test_real_answer_not_flagged(self):
        for s in [
            "✅ 现行版本为 GB 18597—2023，以下技术要求摘自官网 PDF。",
            "# 危险废物贮存执法参考要点\n\n## 一、适用范围",
            "你好，我是 eco Agent",
            "3.14159",
        ]:
            assert _is_llm_unavailable_text(s) is False

    def test_empty_and_nonstring(self):
        assert _is_llm_unavailable_text("") is False
        assert _is_llm_unavailable_text(None) is False
        assert _is_llm_unavailable_text({"a": 1}) is False


class TestSaveRequestRegex:
    """文档类诉求必须命中落盘纪律正则（之前只认 报告/清单，文档/简报漏掉）。"""

    def setup_method(self):
        # 直接引用源码常量，杜绝测试与实现正则漂移
        self.rx = _SAVE_REQUEST_RE

    def test_document_requests_hit(self):
        for q in [
            "生成一份危险废物贮存污染控制标准执法参考要点的 md 文档并保存",
            "把这份要点写成一份正式文档",
            "生成空气质量简报",
            "整理成 word 文档给我",
            "把分析存成报告",
        ]:
            assert self.rx.search(q), q

    def test_plain_chat_misses(self):
        for q in ["你好", "详细讲一下标准的技术要求，分点展开", "什么是超低排放"]:
            assert not self.rx.search(q), q
