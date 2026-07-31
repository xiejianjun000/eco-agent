#!/usr/bin/env python3
"""decisions.py — LLM 决策依据结构化留痕（SM3 链式）

每次 LLM 在 chat_with_tools 中选择/不选择工具时，追加一条留痕到
~/.eco/decisions.jsonl（复用 prompt_engine 的 SM3 链式审计，防篡改可验链）：

  candidate_tools : 候选工具数
  selected_tools  : 本轮选中的工具名列表（空 = 选择直接回答）
  finish_reason   : tool_calls | stop | error
  raw_tool_calls  : 模型原始 tool_calls（选择工具时保留，含 id/参数原文）
  prompt_phase    : 写入时 prompt_engine 三阶段状态机当前阶段
  model/provider  : 决策所用模型

eco doctor 汇总视图：summarize_decisions() 给出调用数、工具选择率、Top 工具等。
"""
from __future__ import annotations

import json
from pathlib import Path

DECISIONS_FILE = Path.home() / ".eco" / "decisions.jsonl"


def get_decision_chain(path: Path | None = None):
    from agent_core.prompt_engine import PromptAuditChain
    return PromptAuditChain(path=path or DECISIONS_FILE)


def _prompt_phase() -> str:
    try:
        from agent_core.prompt_engine import get_prompt_engine
        return get_prompt_engine().phase
    except Exception:
        return ""


def _current_trace_id() -> str:
    """当前活跃 span 树的 OTLP trace_id（与 ~/.eco/traces 互相关联）；无则空串"""
    try:
        from agent_core.observability import current_trace_id
        return current_trace_id()
    except Exception:
        return ""


def record_decision(candidate_tools: int, selected_tools: list[str],
                    finish_reason: str, raw_tool_calls=None,
                    model: str = "", provider: str = "", prompt_phase: str = "",
                    round_idx: int = 0, trace_id: str = "",
                    path: Path | None = None) -> dict:
    """追加一条 LLM 决策留痕（SM3 链）。返回写入的条目。"""
    payload = {
        "candidate_tools": int(candidate_tools),
        "selected_tools": list(selected_tools),
        "finish_reason": finish_reason,
        "raw_tool_calls": raw_tool_calls or [],
        "prompt_phase": prompt_phase or _prompt_phase(),
        "model": model, "provider": provider, "round": round_idx,
        "trace_id": trace_id or _current_trace_id(),
    }
    return get_decision_chain(path).append(
        source="llm_decision",
        content=json.dumps(payload, ensure_ascii=False),
        phase=payload["prompt_phase"], accepted=True,
        reason=f"finish={finish_reason} selected={','.join(selected_tools) or '-'}")


def summarize_decisions(path: Path | None = None) -> dict:
    """汇总 decisions.jsonl：决策数、工具选择率、Top 工具、按 finish_reason 分布"""
    p = Path(path) if path else DECISIONS_FILE
    recs = []
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if entry.get("source") == "llm_decision":
                    recs.append(json.loads(entry.get("content", "{}")))
            except (json.JSONDecodeError, TypeError):
                pass
    total = len(recs)
    with_tools = sum(1 for r in recs if r.get("selected_tools"))
    by_finish: dict[str, int] = {}
    tool_counts: dict[str, int] = {}
    for r in recs:
        fr = r.get("finish_reason", "?")
        by_finish[fr] = by_finish.get(fr, 0) + 1
        for t in r.get("selected_tools") or []:
            tool_counts[t] = tool_counts.get(t, 0) + 1
    top_tools = sorted(tool_counts.items(), key=lambda kv: -kv[1])[:10]
    return {
        "decisions": total,
        "tool_selected": with_tools,
        "tool_select_rate": round(with_tools / total, 3) if total else 0.0,
        "by_finish_reason": by_finish,
        "top_tools": top_tools,
        "decisions_file": str(p),
    }
