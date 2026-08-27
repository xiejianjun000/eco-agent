"""LLM 决策留痕测试：mock 一轮 tool_calls 响应 + 一轮纯文本响应，断言两条留痕结构完整"""
import json

from agent_core.decisions import get_decision_chain, record_decision, summarize_decisions


def _run_two_rounds(monkeypatch, tmp_path):
    dec_file = tmp_path / "decisions.jsonl"
    monkeypatch.setattr("agent_core.decisions.DECISIONS_FILE", dec_file)
    from agent_core.llm_client import LLMClient
    c = LLMClient()
    monkeypatch.setattr(c, "_api_key", "sk-test")
    monkeypatch.setattr(c, "_disabled", False)
    rounds = iter([
        {"role": "assistant", "content": None,
         "tool_calls": [{"id": "call_9", "type": "function",
                         "function": {"name": "search_kb", "arguments": '{"q": "法"}'}}]},
        {"role": "assistant", "content": "直接回答。"},
    ])
    monkeypatch.setattr(c, "_call_chat_with_tools",
                        lambda m, msgs, t: (next(rounds), None))

    async def fake_exec(name, args):
        return "kb hit"

    monkeypatch.setattr("agent_core.tools_registry.execute_tool", fake_exec)
    tools = [{"function": {"name": "search_kb"}}, {"function": {"name": "save_document"}}]
    answer = c.chat_with_tools([{"role": "user", "content": "查法条"}], tools=tools, stream=False)
    assert answer == "直接回答。"
    return dec_file


def test_decision_records_structure(monkeypatch, tmp_path):
    dec_file = _run_two_rounds(monkeypatch, tmp_path)
    lines = [json.loads(l) for l in dec_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 2
    recs = [json.loads(e["content"]) for e in lines]

    r1, r2 = recs
    # 第一轮：选择工具
    assert r1["finish_reason"] == "tool_calls"
    assert r1["candidate_tools"] == 2
    assert r1["selected_tools"] == ["search_kb"]
    assert r1["raw_tool_calls"][0]["function"]["name"] == "search_kb"
    assert r1["raw_tool_calls"][0]["function"]["arguments"] == '{"q": "法"}'
    # 第二轮：纯文本（stop）
    assert r2["finish_reason"] == "stop"
    assert r2["selected_tools"] == []
    assert r2["raw_tool_calls"] == []
    for r in recs:
        assert "prompt_phase" in r and "model" in r and "provider" in r and "round" in r
    # SM3 链完整
    res = get_decision_chain(dec_file).verify_chain()
    assert res["valid"] and res["entries"] == 2


def test_decision_summary(monkeypatch, tmp_path):
    dec_file = _run_two_rounds(monkeypatch, tmp_path)
    s = summarize_decisions(dec_file)
    assert s["decisions"] == 2
    assert s["tool_selected"] == 1
    assert s["tool_select_rate"] == 0.5
    assert s["by_finish_reason"] == {"tool_calls": 1, "stop": 1}
    assert s["top_tools"] == [("search_kb", 1)]


def test_record_decision_direct(monkeypatch, tmp_path):
    dec_file = tmp_path / "d.jsonl"
    monkeypatch.setattr("agent_core.decisions.DECISIONS_FILE", dec_file)
    entry = record_decision(candidate_tools=0, selected_tools=[], finish_reason="stop",
                            model="m", provider="p", prompt_phase="inspection")
    assert entry["source"] == "llm_decision"
    payload = json.loads(entry["content"])
    assert payload["prompt_phase"] == "inspection"
    assert payload["candidate_tools"] == 0
