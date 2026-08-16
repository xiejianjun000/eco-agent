#!/usr/bin/env python3
"""
server/api/chat.py — 对话 API

复用 agent_core.llm_client（chat / chat_stream），
系统提示词由 prompt_engine（SOUL 驱动）构建。
"""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

logger = logging.getLogger("eco.server.chat")

router = APIRouter()


class ChatRequest(BaseModel):
    message: str = Field(..., description="用户消息")
    history: list[dict] = Field(default_factory=list, description="历史消息 [{role, content}]")
    model: str = Field(default="", description="模型名，留空用默认")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)


class ChatResponse(BaseModel):
    reply: str
    model: str
    usage: dict = Field(default_factory=dict)


def _build_messages(message: str, history: list[dict]) -> list[dict]:
    """系统提示词（SOUL 驱动）+ 截断历史 + 当前消息。"""
    from agent_core.prompt_engine import get_prompt_engine

    eng = get_prompt_engine()
    system = eng.build_system_prompt()
    # 法典知识注入：2026-08-15 后法典已施行，纠正通用模型的过时基线
    from datetime import date

    codex_note = (
        f"【重要背景】今天是{date.today().isoformat()}。"
        "《中华人民共和国生态环境法典》已于2026年3月12日通过、"
        "2026年8月15日起施行（共1242条，五编：总则/污染防治/生态保护/绿色低碳发展/"
        "法律责任和附则），《环境保护法》《环境影响评价法》等10部单行法同日废止。"
        "涉及法条引用时，优先调用 statute_lookup/statute_search 工具查法典原文，"
        "不要凭记忆回答法条内容。"
    )
    system = system + "\n" + codex_note
    messages: list[dict] = [{"role": "system", "content": system}]
    for h in history[-20:]:
        if isinstance(h, dict) and h.get("role") in ("user", "assistant"):
            messages.append({"role": h["role"], "content": str(h.get("content", ""))})
    messages.append({"role": "user", "content": message})
    return messages


def _codex_tools() -> list[dict]:
    """法典检索工具（OpenAI tools 格式，供工具循环使用）。"""
    return [
        {
            "type": "function",
            "function": {
                "name": "statute_lookup",
                "description": "生态环境法典条文精确检索——按条号（如1054或第一千零五十四条）返回条文原文",
                "parameters": {
                    "type": "object",
                    "properties": {"article": {"type": "string", "description": "条号"}},
                    "required": ["article"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "statute_search",
                "description": "生态环境法典关键词检索——按关键词（如逃避监管、按日连续处罚）返回条文原文",
                "parameters": {
                    "type": "object",
                    "properties": {"keyword": {"type": "string", "description": "关键词"}},
                    "required": ["keyword"],
                },
            },
        },
    ]


def _run_codex_tool(name: str, arguments: dict) -> str:
    import subprocess
    import sys
    from pathlib import Path

    script = Path(__file__).resolve().parent.parent.parent / "ecoskills" / "eco-codex" / "scripts" / "lookup.py"
    cmd = [sys.executable, str(script), "article" if name == "statute_lookup" else "search",
           str(arguments.get("article") or arguments.get("keyword", ""))]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    return r.stdout.strip() or r.stderr.strip()[:300]


def _extract_reply(result: dict) -> str:
    if isinstance(result, dict) and result.get("_error"):
        detail = result.get("_error_detail", "unknown error")
        return f"[eco-server] LLM 调用失败: {detail}"
    try:
        return result["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return str(result)


@router.post("/chat")
async def chat(req: ChatRequest) -> ChatResponse:
    from agent_core.llm_client import get_default_client

    client = get_default_client()
    messages = _build_messages(req.message, req.history)
    try:
        reply = await _chat_with_codex_loop(client, messages, req.model)
    except Exception as e:  # noqa: BLE001 — API 边界兜底
        logger.exception("chat failed")
        return ChatResponse(reply=f"[eco-server] 对话失败: {e}", model=req.model or "default", usage={})
    usage = client.get_stats() if hasattr(client, "get_stats") else {}
    return ChatResponse(reply=reply, model=req.model or "default", usage=usage)


async def _chat_with_codex_loop(client, messages: list[dict], model: str = "",
                                max_rounds: int = 3) -> str:
    """法典工具循环：LLM 决定查条 → 执行检索 → 结果回填 → 综合回答。"""
    import asyncio
    import json

    tools = _codex_tools()
    for _ in range(max_rounds):
        loop = asyncio.get_event_loop()
        msg, err = await loop.run_in_executor(
            None, lambda: client._call_chat_with_tools(model or client._provider["default_model"],
                                                       messages, tools))
        if err or msg is None:
            return f"[eco-server] LLM 调用失败: {err}"
        tool_calls = msg.get("tool_calls")
        if not tool_calls:
            return str(msg.get("content") or "")
        messages.append({"role": "assistant", "content": msg.get("content") or None,
                         "tool_calls": tool_calls})
        for tc in tool_calls:
            fn = tc.get("function", {})
            name, raw_args = fn.get("name", ""), fn.get("arguments", "{}")
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
            except json.JSONDecodeError:
                args = {}
            result = await loop.run_in_executor(
                None, lambda n=name, a=args: _run_codex_tool(n, a))
            messages.append({"role": "tool", "tool_call_id": tc.get("id", ""),
                             "content": result})
    msg, err = await loop.run_in_executor(
        None, lambda: client._call_chat_with_tools(model or client._provider["default_model"],
                                                   messages, []))
    if err or msg is None:
        return f"[eco-server] LLM 调用失败: {err}"
    return str(msg.get("content") or "")


@router.post("/chat/stream")
async def chat_stream(req: ChatRequest) -> StreamingResponse:
    from agent_core.llm_client import get_default_client

    client = get_default_client()
    messages = _build_messages(req.message, req.history)
    queue: asyncio.Queue[str | None] = asyncio.Queue()

    def on_chunk(text: str) -> None:
        queue.put_nowait(text)

    async def gen():
        loop = asyncio.get_event_loop()

        def _run() -> None:
            try:
                client.chat_stream(messages, on_chunk=on_chunk)
            except Exception as e:  # noqa: BLE001
                logger.exception("chat_stream failed")
                queue.put_nowait(json.dumps({"error": str(e)}))
            finally:
                queue.put_nowait(None)

        await loop.run_in_executor(None, _run)
        while True:
            chunk = await queue.get()
            if chunk is None:
                yield "data: [DONE]\n\n"
                break
            yield f"data: {json.dumps({'delta': chunk})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")
