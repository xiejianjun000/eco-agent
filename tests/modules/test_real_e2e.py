"""真实 e2e 全链路测试（ECO_E2E=1 门控，默认 skip）。

链路：真实 LLM chat_with_tools(stream=True) → 模型返回 tool_calls(save_document)
→ tools_registry.execute_tool 真实执行 → 工作区 deliverables 目录真实落盘校验。

运行方式（需要有效 KIMI_API_KEY 或已配置的备用 provider Key）：
    ECO_E2E=1 pytest tests/modules/test_real_e2e.py -v
"""
import os

import pytest

from agent_core.workspace import WorkspaceManager

# 修复：conftest 为单测强制 ECO_LLM_DISABLE=1，真实 e2e 必须解除该开关，
# 否则 LLMClient.available() 恒为 False，e2e 永远 skip。
if os.environ.get("ECO_E2E") == "1":
    os.environ.pop("ECO_LLM_DISABLE", None)

pytestmark = pytest.mark.skipif(
    os.environ.get("ECO_E2E") != "1",
    reason="真实 e2e 默认跳过；设置 ECO_E2E=1 且配置有效 API Key 后启用",
)


@pytest.fixture()
def ws_manager(tmp_path, monkeypatch):
    """隔离工作区根目录到 tmp_path，避免真实落盘污染用户目录。"""
    mgr = WorkspaceManager(tmp_path)
    monkeypatch.setattr("agent_core.workspace._manager", mgr)
    yield mgr
    monkeypatch.setattr("agent_core.workspace._manager", None)


class TestRealE2E:
    def test_chat_tool_calls_save_document_real_disk(self, ws_manager):
        """chat → tool_calls(save_document) → 真实落盘 全链路。"""
        from agent_core.llm_client import LLMClient
        from agent_core.tools_registry import get_tools

        client = LLMClient()
        if not client.available():
            pytest.skip("未配置有效 API Key（KIMI_API_KEY 或备用 provider）")

        ws = ws_manager.create("e2e真实落盘", category="通用")
        ws_manager.open(ws.meta["slug"])

        tools = [t for t in get_tools() if t["function"]["name"] == "save_document"]
        assert tools, "tools_registry 中应存在 save_document"

        chunks = []
        answer = client.chat_with_tools(
            messages=[
                {"role": "system",
                 "content": "你是生态环境执法文书助手。凡需保存文件，必须调用 save_document 工具，"
                            "不得凭空声称已保存。"},
                {"role": "user",
                 "content": "请把以下内容保存为 e2e-check.md：合力砖厂排污许可证编号 "
                            "XS-2024-001，有效期至 2026-12-31。保存后用一句话确认。"},
            ],
            tools=tools, stream=True, on_chunk=chunks.append,
        )

        deliv = ws.path / "deliverables"
        files = list(deliv.glob("e2e-check*.md")) if deliv.is_dir() else []
        assert files, f"模型未通过 save_document 真实落盘，回答：{answer[:300]}"
        text = files[0].read_text(encoding="utf-8")
        assert "XS-2024-001" in text, f"落盘内容缺少关键事实：{text[:300]}"
        assert answer and "[API 错误]" not in answer

    def test_stream_chunks_arrive_incrementally(self, ws_manager):
        """真实流式：on_chunk 应收到多段增量 content（非一次性整段）。"""
        from agent_core.llm_client import LLMClient

        client = LLMClient()
        if not client.available():
            pytest.skip("未配置有效 API Key（KIMI_API_KEY 或备用 provider）")

        chunks = []
        answer = client.chat_with_tools(
            messages=[{"role": "user",
                       "content": "用三句话介绍生态环境执法中的“双随机一公开”，不要调用任何工具。"}],
            tools=[], stream=True, on_chunk=chunks.append,
        )
        content_chunks = [c for c in chunks if c and not c.startswith("\n")]
        assert answer and "[API 错误]" not in answer
        assert len(content_chunks) >= 2, f"流式应逐段到达，实际 {len(content_chunks)} 段"
