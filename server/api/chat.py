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
    duration_ms: int = Field(default=0, description="总耗时（毫秒）")
    ttft_ms: int = Field(default=0, description="首 token 耗时（毫秒）")
    trace: list[dict] = Field(default_factory=list, description="执行轨迹（思考/工具调用/耗时）")


def _load_codex_skill_rules() -> str:
    """加载 eco-codex skill 的检索规则（SKILL.md 全文注入系统提示词）。"""
    from pathlib import Path

    skill_md = (Path(__file__).resolve().parent.parent.parent
                / "ecoskills" / "eco-codex" / "SKILL.md")
    try:
        return skill_md.read_text(encoding="utf-8")
    except OSError:
        return ""


def _build_messages(message: str, history: list[dict]) -> list[dict]:
    """系统提示词（SOUL 驱动）+ 法典 skill 规则 + 截断历史 + 当前消息。"""
    from datetime import date

    from agent_core.prompt_engine import get_prompt_engine

    eng = get_prompt_engine()
    system = eng.build_system_prompt()

    # 法典知识注入：2026-08-15 后法典已施行，纠正通用模型的过时基线
    codex_note = (
        f"【重要背景】今天是{date.today().isoformat()}。"
        "《中华人民共和国生态环境法典》已于2026年3月12日通过、"
        "2026年8月15日起施行（共1242条，五编：总则/污染防治/生态保护/绿色低碳发展/"
        "法律责任和附则），《环境保护法》《环境影响评价法》等10部单行法同日废止。\n"
    )
    skill_rules = _load_codex_skill_rules()
    if skill_rules:
        codex_note += (
            "\n【工具使用纪律——必须遵守】\n"
            "1. 涉及法条/条款/处罚幅度的问题，必须实际调用 statute_lookup 或 statute_search 工具获取原文，"
            "拿到结果后再回答；禁止凭记忆说法条。\n"
            "2. 涉及案卷评查/执法实务/督察经验等问题，用 kb_search 或 kb_semantic_search 检索知识库。\n"
            "3. 工具调用只能通过 function calling 机制发出；禁止在文本里用 <invoke> 标签"
            "或任何文本形式模拟工具调用，禁止编造不存在的工具名（只有上述四个工具）。\n"
            "4. 禁止输出'正在调用工具''请稍候'之类的话——直接调用工具，不要预告。\n"
            "5. 引用条文必须与工具返回的原文一致，条号以工具结果为准。\n"
        )
    system = system + "\n" + codex_note
    messages: list[dict] = [{"role": "system", "content": system}]
    for h in history[-20:]:
        if isinstance(h, dict) and h.get("role") in ("user", "assistant"):
            messages.append({"role": h["role"], "content": str(h.get("content", ""))})
    messages.append({"role": "user", "content": message})
    return messages


def _codex_tools() -> list[dict]:
    """法典 + 知识库检索工具（OpenAI tools 格式，供工具循环使用）。"""
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
        {
            "type": "function",
            "function": {
                "name": "kb_search",
                "description": "执法知识库全文搜索（案卷评查/执法办案/督察/法规解读等实战资料，自动识别角色加权）",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string", "description": "检索关键词或短句"}},
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "kb_semantic_search",
                "description": "执法知识库语义搜索（向量检索，理解自然语言含义，适合自然语言问题）",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string", "description": "自然语言问题"}},
                    "required": ["query"],
                },
            },
        },
    ]


async def _run_tool(name: str, arguments: dict) -> str:
    """工具分发：statute_* 走本地法典库，kb_* 走 ehs-kb-ops MCP 知识库。"""
    if name.startswith("statute_"):
        import subprocess
        import sys
        from pathlib import Path

        script = Path(__file__).resolve().parent.parent.parent / "ecoskills" / "eco-codex" / "scripts" / "lookup.py"
        cmd = [sys.executable, str(script), "article" if name == "statute_lookup" else "search",
               str(arguments.get("article") or arguments.get("keyword", ""))]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        return r.stdout.strip() or r.stderr.strip()[:300]
    if name.startswith("kb_"):
        from agent_core.tools_registry import attach_mcp_tools, execute_tool

        attach_mcp_tools()
        full = f"mcp__ehs_kb__{name}"
        arg_map = {"kb_search": "query", "kb_semantic_search": "query"}
        result = await execute_tool(full, {arg_map.get(name, "query"): arguments.get("query", "")})
        # 截断长结果（知识库返回目录级列表，过长会稀释模型注意力）
        return result[:2000]
    return f"未知工具: {name}"


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
    import time

    from agent_core.llm_client import get_default_client

    client = get_default_client()
    messages = _build_messages(req.message, req.history)
    t0 = time.monotonic()
    try:
        reply, trace = await _chat_with_codex_loop(client, messages, req.model)
    except Exception as e:  # noqa: BLE001 — API 边界兜底
        logger.exception("chat failed")
        return ChatResponse(reply=f"[eco-server] 对话失败: {e}", model=req.model or "default", usage={})
    duration_ms = int((time.monotonic() - t0) * 1000)
    usage = client.get_stats() if hasattr(client, "get_stats") else {}
    # 轨迹审计入链（govmcp SM3，五要素）
    try:
        from agent_core.trace_audit import get_trace_audit

        get_trace_audit().record_trace(req.message, reply, len(trace), duration_ms,
                                       model=req.model or client._provider["default_model"])
    except Exception as e:  # noqa: BLE001 — 审计失败不阻断业务
        logger.warning("trace audit failed: %s", e)
    # 非流式：首 token 约等于总耗时（无中间增量）
    return ChatResponse(reply=reply, model=req.model or "default", usage=usage,
                        duration_ms=duration_ms, ttft_ms=duration_ms, trace=trace)


async def _chat_with_codex_loop(client, messages: list[dict], model: str = "",
                                max_rounds: int = 3) -> tuple[str, list[dict]]:
    """法典工具循环：LLM 决定查条 → 执行检索 → 结果回填 → 综合回答。

    返回 (reply, trace)：trace 为 DSH 式执行轨迹（思考轮/工具调用/耗时），
    供 Web UI 折叠展示与 trace_audit 审计入链。

    兜底：模型输出"正在调用工具"之类空话但未真正调用时，追加纠偏消息
    强制其实际调用工具（空话绝不作为最终回复返回）。
    """
    import asyncio
    import json
    import re
    import time

    from agent_core.trace_audit import get_trace_audit

    audit = get_trace_audit()
    tools = _codex_tools()
    trace: list[dict] = []
    empty_talk_re = re.compile(
        r"正在(调用|查询|检索|获取|调取)|请稍候|稍等|马上(为您)?(查询|检索)|我先(查|检索)"
        r"|待工具返回|待.*填入|（此处待|占位）|<invoke|invoke name|kb_get_document|让我直接"
    )
    round_idx = 0
    for _ in range(max_rounds):
        round_idx += 1
        loop = asyncio.get_event_loop()
        t_llm = time.monotonic()
        msg, err = await loop.run_in_executor(
            None, lambda: client._call_chat_with_tools(model or client._provider["default_model"],
                                                       messages, tools))
        llm_ms = int((time.monotonic() - t_llm) * 1000)
        if err or msg is None:
            return f"[eco-server] LLM 调用失败: {err}", trace
        audit.record_llm_call(model or client._provider["default_model"],
                              round_idx, llm_ms)
        tool_calls = msg.get("tool_calls")
        if not tool_calls:
            content = str(msg.get("content") or "")
            # 空话检测：提及调用工具但未真调用 → 纠偏重试
            if empty_talk_re.search(content):
                trace.append({"type": "correction", "round": round_idx,
                              "note": "空话纠偏", "cost_ms": llm_ms})
                messages.append({"role": "assistant", "content": content})
                messages.append({
                    "role": "user",
                    "content": "你刚才没有实际调用工具，只输出了预告文字。"
                               "请直接调用 statute_lookup 或 statute_search 获取条文原文，"
                               "基于工具返回的真实结果回答，不要再输出预告。",
                })
                continue
            trace.append({"type": "answer", "round": round_idx, "cost_ms": llm_ms,
                          "chars": len(content)})
            return content, trace
        trace.append({"type": "think", "round": round_idx, "cost_ms": llm_ms,
                      "tools": [tc["function"]["name"] for tc in tool_calls],
                      "thought": (str(msg.get("content") or "")[:100])})
        messages.append({"role": "assistant", "content": msg.get("content") or None,
                         "tool_calls": tool_calls})
        # 并行执行同轮全部工具调用（4 个串行是 12s+ 延迟的主因）
        async def _exec_one(tc):
            fn = tc.get("function", {})
            name, raw_args = fn.get("name", ""), fn.get("arguments", "{}")
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
            except json.JSONDecodeError:
                args = {}
            t_tool = time.monotonic()
            try:
                result = await _run_tool(name, args)
            except Exception as e:  # noqa: BLE001 — 单工具失败不拖垮整轮
                logger.warning("tool %s failed: %s", name, e)
                result = f"工具执行失败: {e}"
            tool_ms = int((time.monotonic() - t_tool) * 1000)
            return tc.get("id", ""), name, args, result, tool_ms

        results = await asyncio.gather(*[_exec_one(tc) for tc in tool_calls])
        for tool_call_id, name, args, result, tool_ms in results:
            # 轨迹事件（UI 展示）
            trace.append({"type": "tool", "round": round_idx, "name": name,
                          "category": _tool_category(name),
                          "args": args, "result_preview": str(result)[:200],
                          "cost_ms": tool_ms})
            # govmcp SM3 审计入链（五要素，等保）
            audit.record_tool_call(name, args, result, tool_ms,
                                   level=_tool_level(name), decision="allow")
            messages.append({"role": "tool", "tool_call_id": tool_call_id,
                             "content": result})
    # 循环耗尽：追加总结指令，强制基于已检索结果直接回答
    messages.append({
        "role": "user",
        "content": "工具检索已完成。请基于上面工具返回的真实结果，"
                   "直接给出最终回答（不要再调用工具，不要输出工具调用格式）。"
                   "如果结果不足以回答，就基于已有内容作答并标注局限。",
    })
    msg, err = await loop.run_in_executor(
        None, lambda: client._call_chat_with_tools(model or client._provider["default_model"],
                                                   messages, []))
    if err or msg is None:
        return f"[eco-server] LLM 调用失败: {err}", trace
    content = str(msg.get("content") or "")
    # 幻觉兜底：仍输出工具调用格式（含全角变体）→ 最强约束重试一次
    if "tool_calls" in content or "invoke" in content:
        trace.append({"type": "correction", "round": round_idx, "note": "幻觉格式纠偏"})
        messages.append({"role": "user",
                         "content": "禁止输出 tool_calls、invoke 等任何工具调用格式（含全角符号），"
                                    "现在只输出给用户的最终文字回答。"})
        msg2, err2 = await loop.run_in_executor(
            None, lambda: client._call_chat_with_tools(
                model or client._provider["default_model"], messages, []))
        if err2 is None and msg2 is not None:
            content = str(msg2.get("content") or "")
    # 末层兜底：贪婪剥离未闭合的工具调用残留（半角/全角通吃）
    content = re.sub(r"[<＜]tool_calls>[\s\S]*$", "", content).strip()
    content = re.sub(r"[<＜]invoke[\s\S]*$", "", content).strip()
    trace.append({"type": "answer", "round": round_idx, "chars": len(content)})
    return (content or "[eco-server] 模型未给出有效回答"), trace


def _tool_level(name: str) -> str:
    """工具风险级（审计台账用）。"""
    if name.startswith("statute_") or name in ("kb_search", "kb_semantic_search"):
        return "L1"
    if name in ("kb_upload", "kb_delete", "kb_sync"):
        return "L3"
    return "L2"


def _tool_category(name: str) -> str:
    """工具动作分类（轨迹标签用）: read / write / exec。"""
    read_tools = ("statute_lookup", "statute_search", "kb_search", "kb_semantic_search",
                  "kb_read", "kb_list", "kb_status", "file_read", "git_status")
    write_tools = ("kb_upload", "kb_delete", "kb_sync", "file_write")
    if name in read_tools or name.startswith("statute_"):
        return "read"
    if name in write_tools:
        return "write"
    return "exec"


@router.post("/chat/stream")
async def chat_stream(req: ChatRequest) -> StreamingResponse:
    """流式对话——与 /chat 相同的法典工具循环（保证真实查询），
    循环完成后按小片 SSE 输出（保留逐字呈现体验）。

    ttft_ms 语义：模型+工具循环的准备耗时（首个可见字符出现时刻）。
    """
    import time

    from agent_core.llm_client import get_default_client

    client = get_default_client()
    messages = _build_messages(req.message, req.history)
    t0 = time.monotonic()

    async def gen():
        # 工具循环（与 /chat 相同逻辑：法典查询 + 空话兜底）
        try:
            reply, trace = await _chat_with_codex_loop(client, messages, req.model)
        except Exception as e:  # noqa: BLE001
            logger.exception("chat_stream failed")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            yield "data: [DONE]\n\n"
            return

        prep_ms = int((time.monotonic() - t0) * 1000)
        # 轨迹事件（前端折叠展示）
        yield f"data: {json.dumps({'trace': trace}, ensure_ascii=False)}\n\n"
        # 小片输出：6 字符/片 + 微小间隔，保留流式节奏
        step = 6
        for i in range(0, len(reply), step):
            payload = {"delta": reply[i:i + step]}
            if i == 0:
                payload["ttft_ms"] = prep_ms
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0.02)
        done_payload = json.dumps({"done": True, "duration_ms": int((time.monotonic() - t0) * 1000)})
        yield f"data: {done_payload}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")
