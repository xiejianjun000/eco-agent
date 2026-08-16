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
    messages: list[dict] = [{"role": "system", "content": system}]
    for h in history[-20:]:
        if isinstance(h, dict) and h.get("role") in ("user", "assistant"):
            messages.append({"role": h["role"], "content": str(h.get("content", ""))})
    messages.append({"role": "user", "content": message})
    return messages


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
        result = client.chat(messages, model=req.model, temperature=req.temperature)
    except Exception as e:  # noqa: BLE001 — API 边界兜底
        logger.exception("chat failed")
        return ChatResponse(reply=f"[eco-server] 对话失败: {e}", model=req.model or "default", usage={})
    reply = _extract_reply(result)
    usage = client.get_stats() if hasattr(client, "get_stats") else {}
    return ChatResponse(reply=reply, model=req.model or "default", usage=usage)


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
