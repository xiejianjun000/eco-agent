"""记忆系统 + Token 压缩测试"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from agent_core.data_sync import TokenCompressor
from agent_core.memory_viz import MemoryViz

class TestTokenCompression:
    def test_compression_ratio(self):
        tc = TokenCompressor()
        text = "关键信息" * 20000 + "\n" + "\n".join(f"第{i}条重要数据" for i in range(100))
        result = tc.compress(text)
        assert result['ratio'] < 0.5, f"压缩比{result['ratio']}需<0.5"

    def test_rag_accuracy(self):
        tc = TokenCompressor()
        text = "关键信息" * 5000
        r = tc.compress(text)
        acc = tc.rag_accuracy(text[:5000], r['compressed'][:3000])
        assert acc >= 0.9, f"RAG准确率{acc}需>=0.9"

class TestMemoryViz:
    def test_graph_output(self):
        mv = MemoryViz()
        graph = mv.get_graph()
        assert 'nodes' in graph
        assert 'edges' in graph

    def test_user_override(self):
        mv = MemoryViz()
        r = mv.update_node("test_node", {"title": "用户编辑"})
        assert r['success'] is True

    def test_delete_and_merge(self):
        mv = MemoryViz()
        assert mv.delete_node("del_node")['success'] is True
        assert mv.merge_nodes("target", ["a", "b"])['success'] is True
