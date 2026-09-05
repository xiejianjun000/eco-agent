#!/usr/bin/env python3
"""
agent_core/compaction.py — 上下文压缩（对标 DSH compaction + 验收 D-03）

策略:
  - should_compact(messages, max_tokens) 按估算 token 超限判定
  - compact(messages) 用 LLM 提炼早期消息为摘要 checkpoint，
    替换被压缩区间；LLM 不可用时降级为"保留尾部 + 前缀截断摘要"
  - 压缩动作写入 SessionEventLog（compaction/summary 事件，log-only 语义）
  - D-03 验收口径: 压缩后 token < 原始 50%，摘要保真由调用方评测
"""

from __future__ import annotations

import logging

logger = logging.getLogger("eco.compaction")

# 估算：1 token ≈ 3.5 字符（中英混合近似），留安全余量
_CHARS_PER_TOKEN = 3.5


def estimate_tokens(messages: list[dict]) -> int:
    total = 0
    for m in messages:
        content = m.get("content") or ""
        total += max(1, int(len(str(content)) / _CHARS_PER_TOKEN))
    return total


def should_compact(messages: list[dict], max_tokens: int = 8000) -> bool:
    """当前消息估算 token 是否超限。"""
    return estimate_tokens(messages) > max_tokens


def _truncate_summary(messages: list[dict], keep_tail: int = 6) -> list[dict]:
    """无 LLM 降级：前缀消息压成结构摘要，保留尾部 keep_tail 条。"""
    if len(messages) <= keep_tail:
        return messages
    head = messages[:-keep_tail]
    tail = messages[-keep_tail:]
    summary_parts = []
    for m in head:
        role = m.get("role", "?")
        content = str(m.get("content", ""))[:60].replace("\n", " ")
        summary_parts.append(f"[{role}] {content}")
    summary = {"role": "system", "content": "【上下文摘要（截断降级）】早期对话要点：\n" + "\n".join(summary_parts)}
    return [summary] + tail


def compact(messages: list[dict], session_log=None, session_id: str = "", max_tokens: int = 8000) -> dict:
    """压缩消息列表，返回 {messages, summary, tokens_before, tokens_after, method}。"""
    tokens_before = estimate_tokens(messages)
    if not should_compact(messages, max_tokens):
        return {
            "messages": messages,
            "summary": None,
            "tokens_before": tokens_before,
            "tokens_after": tokens_before,
            "method": "noop",
        }

    summary_text = _llm_summary(messages)
    if summary_text:
        method = "llm"
    else:
        method = "truncate"
        summary_text = None

    if method == "llm":
        keep_tail = max(2, len(messages) // 6)
        tail = messages[-keep_tail:]
        compacted = [{"role": "system", "content": "【上下文压缩摘要】早期对话要点：\n" + summary_text}] + tail
    else:
        compacted = _truncate_summary(messages)

    # 记录压缩事件（log-only，不影响对话流）
    if session_log is not None and session_id:
        try:
            session_log.append(
                "compaction/summary",
                {
                    "tokens_before": tokens_before,
                    "tokens_after": estimate_tokens(compacted),
                    "method": method,
                    "summary": (summary_text or "")[:500],
                },
            )
        except Exception as e:  # noqa: BLE001 — 日志失败不阻断压缩
            logger.warning("compaction 事件记录失败: %s", e)

    return {
        "messages": compacted,
        "summary": summary_text,
        "tokens_before": tokens_before,
        "tokens_after": estimate_tokens(compacted),
        "method": method,
    }


def _llm_summary(messages: list[dict], max_head: int = 30) -> str | None:
    """用 LLM 提炼早期消息摘要；不可用/失败返回 None（调用方降级）。"""
    try:
        from agent_core.llm_client import get_default_client

        client = get_default_client()
        if not client.available():
            return None
        head = messages[:max_head]
        transcript = "\n".join(f"{m.get('role')}: {str(m.get('content'))[:300]}" for m in head)
        prompt = "请把以下对话提炼为不超过 200 字的要点摘要，保留关键事实、数字、结论与待办：\n\n" + transcript[:6000]
        result = client.chat([{"role": "user", "content": prompt}], temperature=0.3)
        if isinstance(result, dict) and result.get("_error"):
            return None
        try:
            text = result["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            return None
        return str(text)[:800] or None
    except Exception as e:  # noqa: BLE001
        logger.warning("LLM 摘要失败，降级截断: %s", e)
        return None
