"""记忆系统 + Token 压缩测试——真实数据内容断言，RAG 准确率如实计算"""
import sys
import os
import re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
import pytest
import agent_core.memory_viz as mv_mod
from agent_core.data_sync import TokenCompressor
from agent_core.memory_viz import MemoryViz


def _keywords(t):
    return set(re.findall(r'[一-鿿]{2,4}|\d+|[a-zA-Z]{3,}', t))


class TestTokenCompression:
    def test_compression_ratio_real(self):
        """压缩比按 Token 估算如实计算，且与独立重算一致"""
        tc = TokenCompressor()
        text = "关键信息" * 20000 + "\n" + "\n".join(f"第{i}条重要数据" for i in range(100))
        result = tc.compress(text)
        assert result["compressed_chars"] < result["original_chars"]
        expected = round(result["compressed_tokens"] / result["original_tokens"], 3)
        assert result["ratio"] == expected, "ratio 必须等于 compressed/original 的真实比值"
        assert 0 < result["ratio"] < 0.5

    def test_short_text_skipped(self):
        tc = TokenCompressor()
        r = tc.compress("短文本")
        assert r["method"] == "skip" and r["ratio"] == 1.0

    def test_rag_accuracy_honest(self):
        """RAG 准确率 = 原文关键词保留率：无封顶、无保底、可独立复算"""
        tc = TokenCompressor()
        text = "关键信息" * 5000
        r = tc.compress(text)
        acc = tc.rag_accuracy(text, r["compressed"])
        kw_o, kw_c = _keywords(text), _keywords(r["compressed"])
        assert acc == round(len(kw_o & kw_c) / len(kw_o), 4)

    def test_rag_accuracy_zero_when_all_lost(self):
        """关键词全丢时必须如实返回 0.0（原实现有 0.85 保底，已修复）"""
        tc = TokenCompressor()
        assert tc.rag_accuracy("甲乙丙丁 12345 hello", "完全无关 unrelated xyz") == 0.0

    def test_rag_accuracy_one_when_identical(self):
        tc = TokenCompressor()
        assert tc.rag_accuracy("完全相同 123", "完全相同 123") == 1.0


@pytest.fixture
def mv(tmp_path, monkeypatch):
    monkeypatch.setattr(mv_mod, "DATA_DIR", tmp_path)
    return MemoryViz()


class TestMemoryViz:
    def test_graph_structure(self, mv):
        graph = mv.get_graph()
        assert isinstance(graph["nodes"], list) and isinstance(graph["edges"], list)
        assert graph["total_nodes"] == len(graph["nodes"])
        assert graph["total_edges"] == len(graph["edges"])

    def test_user_override_persisted(self, mv, tmp_path):
        r = mv.update_node("test_node", {"title": "用户编辑"})
        assert r == {"success": True, "node_id": "test_node"}
        # 副作用断言：覆盖必须落盘，新实例可见
        mv2 = MemoryViz()
        assert mv2.get_stats()["overrides"] >= 1

    def test_delete_and_merge(self, mv):
        assert mv.delete_node("del_node") == {"success": True, "node_id": "del_node"}
        r = mv.merge_nodes("target", ["a", "b"])
        assert r["success"] is True and r["target"] == "target" and r["sources"] == ["a", "b"]
