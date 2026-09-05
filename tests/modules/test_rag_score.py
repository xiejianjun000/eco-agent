"""rag_score 忠实度核验测试（vendored from taiji-verify）+ MCP 工具接入

P1 目标：法规答案生成后对照原文做忠实度评分，幻觉风险预警（D1/D12 抓手）。
"""

import importlib.util
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
from agent_core.rag_score import RAGScorer

SOURCE = "大气污染防治法第九十九条：违反本法规定，超过大气污染物排放标准排放大气污染物的，由县级以上人民政府生态环境主管部门责令改正或者限制生产、停产整治，并处十万元以上一百万元以下的罚款。"  # noqa: E501


class TestRAGScorer:
    """vendored 评分器本体：忠实/幻觉两端必须可区分"""

    def test_faithful_answer_low_risk(self):
        """答案 claims 全部出自原文 → 高忠实度、低幻觉风险"""
        scorer = RAGScorer()
        answer = "根据大气污染防治法第九十九条，超标排放大气污染物的，处十万元以上一百万元以下罚款。"
        r = scorer.score("超标排放罚多少", answer, [SOURCE])
        assert r.faithfulness_score >= 0.6, f"忠实答案忠实度过低: {r.faithfulness_score}"
        assert r.hallucination_risk <= 0.4
        assert r.is_low_risk or not r.is_high_risk

    def test_hallucinated_answer_high_risk(self):
        """答案编造原文没有的条款/数字 → 低忠实度、高幻觉风险"""
        scorer = RAGScorer()
        answer = (
            "根据大气污染防治法第八百八十八条，超标排放一律吊销营业执照，"
            "并处五百万元以上一千万元以下罚款，责任人判处十年有期徒刑。"
        )
        r = scorer.score("超标排放罚多少", answer, [SOURCE])
        assert r.faithfulness_score < 0.6, f"幻觉答案忠实度过高: {r.faithfulness_score}"
        assert r.hallucination_risk > 0.4

    def test_result_to_dict_complete(self):
        """to_dict 必须含三维分数 + 幻觉风险（MCP 返回格式契约）"""
        scorer = RAGScorer()
        r = scorer.score("q", "a", ["c"])
        d = r.to_dict()
        assert {"faithfulness_score", "relevance_score", "completeness_score", "hallucination_risk", "overall_score"} <= set(d)


def _load_mcp():
    """按文件路径加载 MCP 服务脚本（文件名含连字符，不能常规 import）"""
    path = os.path.join(os.path.dirname(__file__), "../../_scripts/eco-knowledge-mcp.py")
    spec = importlib.util.spec_from_file_location("eco_knowledge_mcp", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestFaithfulnessCheckTool:
    """eco-knowledge-mcp 新增 eco_faithfulness_check 工具"""

    def test_tool_registered(self):
        mcp = _load_mcp()
        names = [t["name"] for t in mcp.TOOLS]
        assert "eco_faithfulness_check" in names, f"工具未注册: {names}"

    def test_check_with_inline_source(self):
        """answer + source 内联文本 → 返回三维分数与风险等级"""
        mcp = _load_mcp()
        resp = mcp.handle_tool_call(
            1,
            "eco_faithfulness_check",
            {
                "answer": "超标排放处十万元以上一百万元以下罚款。",
                "source": SOURCE,
                "query": "超标排放罚多少",
            },
        )
        assert "error" not in resp, f"调用失败: {resp.get('error')}"
        content = json.loads(resp["result"]["content"][0]["text"])
        assert "faithfulness_score" in content
        assert "hallucination_risk" in content
        assert content["risk_level"] in ("low", "medium", "high")

    def test_hallucinated_answer_flagged(self):
        """编造条款必须被判中高风险"""
        mcp = _load_mcp()
        resp = mcp.handle_tool_call(
            1,
            "eco_faithfulness_check",
            {
                "answer": "根据第八百八十八条，超标排放判处十年有期徒刑并罚款五千万元。",
                "source": SOURCE,
            },
        )
        content = json.loads(resp["result"]["content"][0]["text"])
        assert content["risk_level"] in ("medium", "high"), f"幻觉答案未被标记: {content}"

    def test_missing_source_and_statute_errors(self):
        """既不给 source 也不给 statute → 明确报错（不静默打分）"""
        mcp = _load_mcp()
        resp = mcp.handle_tool_call(1, "eco_faithfulness_check", {"answer": "任意答案"})
        assert "error" in resp or "error" in json.dumps(resp, ensure_ascii=False).lower()
