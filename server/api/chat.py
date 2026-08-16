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
    session_id: str = Field(default="", description="会话 id，留空用 default（消息落盘/恢复用）")


def _persist_turn(session_id: str, user_msg: str, reply: str, ok: bool) -> None:
    """对话轮次落盘（session_log SHA-256 链，重启可恢复）。"""
    try:
        from agent_core.session_log import SessionEventLog

        slog = SessionEventLog(f"web/{session_id or 'default'}")
        slog.append("user/message", {"content": user_msg})
        if ok and reply:
            slog.append("assistant/message", {"content": reply[:8000]})
    except Exception:  # noqa: BLE001 — 落盘失败不影响主流程
        logger.warning("session persist failed: %s", session_id)


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
            "拿到结果后再回答；禁止凭记忆说法条。statute_search 单次返回约12条且存在截断（truncated=true\n"
            "   表示可能还有未返回的命中），不能保证目标条号排进结果；宽泛词检索只作定位辅助，\n"
            "   精确条号以 statute_lookup 直查为准（如暗管偷排=第164/1108条，危废无证=第534/1178条）。\n"
            "2. 涉及案卷评查/执法实务/督察经验等问题，用 kb_search 或 kb_semantic_search 检索知识库。\n"
            "3. 工具调用只能通过 function calling 机制发出；禁止在文本里用 <invoke> 标签"
            "或任何文本形式模拟工具调用，禁止编造不存在的工具名（只有上述四个工具）。\n"
            "4. 禁止输出'正在调用工具''请稍候'之类的话——直接调用工具，不要预告。\n"
            "5. 引用条文必须与工具返回的原文一致，条号以工具结果为准。\n"
            "6. 用户要求生成文件（PPT/Word/Excel）时，必须调用对应工具（如 generate_pptx）\n"
            "   产出真实文件并返回文件路径；禁止只输出文字大纲声称已交付。\n"
            "7. 【generate_pptx 已在本轮工具列表中】用户说'生成PPT/做课件/出演示文稿'时，\n"
            "   立即调用 generate_pptx(slides=[{\"title\":\"页标题\",\"bullets\":[\"要点\"]}], title=名称)，\n"
            "   然后把工具返回的 path 文件路径告诉用户。不要先写文字大纲再问要不要文件。\n"
            "8. 【你有联网能力】web_fetch 工具可抓取政务网站正文（mee.gov.cn 等白名单），\n"
            "   execute_code 沙箱也可发起网络请求。用户要求查官网文件/最新政策时，\n"
            "   先尝试 web_fetch 实际抓取；禁止声称'没有联网权限'——除非抓取本身失败。\n"
            "9. 【督察资料检索路由——实测固化的官方渠道】\n"
            "   督察动态/典型案例: mee.gov.cn/ywgz/zysthjbhdc/（进驻dcjz/整改dczg/管理dcjl）；\n"
            "   六大区域督察局子站: hbdc/hddc/hndc/xbdc/xndc/dbdc.mee.gov.cn；\n"
            "   制度文件（《督察工作规定》《条例》等党内法规）: 中办国办印发，\n"
            "   《生态环境保护督察工作条例》2025-03-31 中央政治局会议审议批准、\n"
            "   2025-04-28 中共中央、国务院发布（2025-05-12 新华社受权通稿）；\n"
            "   gov.cn 政策库实测未收录（官方搜索返回无结果），原文以新华社通稿+\n"
            "   政务站点转载为准，如首都之窗全文页\n"
            "   beijing.gov.cn/ywdt/dzyjs/202505/t20250513_4087784.html（HTTP 200 实测可访问）；\n"
            "   gov.cn 查不到时如实说明，禁止编造 gov.cn 链接。\n"
            "10. 【法律适用层级——督察条例不是处罚依据】\n"
            "   《生态环境保护督察工作条例》是党内法规，是督察工作的组织依据，\n"
            "   不是行政处罚的实体/程序依据。涉及现场执法、裁量幅度、处罚决定时，\n"
            "   必须用 statute_lookup 调取《生态环境法典》法律责任编等国家法律条文；\n"
            "   督察条例只能作为督察制度背景引用，禁止拿它顶法律条款或作处罚依据。\n"
            "11. 【领域边界——声明之后立即停，绝不越界硬聊】\n"
            "   你是生态环境执法垂直智能体。遇到非生态环境领域的问题（软件开发/前端/运维/\n"
            "   通用编程/其他行业等），只做两件事：① 如实声明能力边界；② 引导用户提出\n"
            "   生态环境业务问题。声明完边界后立即停止该话题，禁止输出任何领域外的\n"
            "   技术分析、'通用经验'、方案对比或推测性建议——即使以'这只是通用经验'\n"
            "   开头也不行；拒绝之后不得补充任何凭记忆的领域外技术内容。\n"
            "   特别注意：'写脚本/写代码/搭系统/做平台/建模型'等请求的执行方式是软件开发，\n"
            "   即使主题是环保（如'CEMS 分析脚本''超标预警系统'），也只输出业务判定逻辑\n"
            "   与法律依据（折算规则、有效性判定、对应法典条款），不输出任何代码实现。\n"
        )
    system = system + "\n" + codex_note
    # 技能目录匹配注入（对标 DSH skill 会话注入）：消息命中触发词的技能全文带上
    try:
        from agent_core.skill_dir import get_skill_dir_registry

        matched = get_skill_dir_registry().match(message, top_n=2)
        for skill in matched:
            if skill.get("name") == "eco-codex":
                continue  # eco-codex 规则已整本注入，跳过避免重复
            body = (skill.get("body") or "")[:6000]
            if body.strip():
                system += (f"\n\n【技能注入：{skill['name']} — {skill.get('description', '')}】\n"
                           + body)
    except Exception:  # noqa: BLE001 — 技能注入失败不影响主流程
        logger.warning("skill match inject failed")
    # 历史教训注入（自愈闭环：此前踩过的坑自动带上，不用人工改提示词）
    try:
        from agent_core.lessons import get_lesson_store

        related = get_lesson_store().search(message)
        if related:
            lines = ["【历史经验——此前处理类似问题的真实记录】"]
            for i, l in enumerate(related, 1):
                lines.append(f"{i}. {l.get('lesson', '')}")
            system = system + "\n" + "\n".join(lines)
    except Exception:  # noqa: BLE001 — 经验注入失败不影响主流程
        pass
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
        {
            "type": "function",
            "function": {
                "name": "execute_code",
                "description": "在沙箱中执行 Python 代码（Docker/bwrap 隔离 + 超时限制）。"
                               "用于数据计算、超标倍数计算、日期推算等。"
                               "受 L3 权限闸门保护：非白名单执行会被拒绝并返回拒绝原因。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string", "description": "Python 代码"},
                        "language": {"type": "string", "description": "语言（默认 python）"},
                    },
                    "required": ["code"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "web_fetch",
                "description": "抓取网页正文（政务站点白名单：gov.cn/mee.gov.cn 等官方来源）。"
                               "用于查生态环境部官网文件、政策通知原文。返回标题+正文纯文本。",
                "parameters": {
                    "type": "object",
                    "properties": {"url": {"type": "string", "description": "完整 URL（http/https）"}},
                    "required": ["url"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "generate_pptx",
                "description": "生成 PowerPoint 演示文稿（.pptx 真实文件）——多页标题+要点，返回真实文件路径。"
                               "用于执法培训课件、案卷评查通报、督察汇报 PPT。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "slides": {
                            "type": "array",
                            "description": "每页: {title, bullets}",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "title": {"type": "string"},
                                    "bullets": {"type": "array", "items": {"type": "string"}},
                                },
                                "required": ["title"],
                            },
                        },
                        "title": {"type": "string", "description": "演示文稿名称"},
                    },
                    "required": ["slides"],
                },
            },
        },
    ]


# 政务站点白名单（等保视角：默认仅允许政务/官方站点，可环境变量扩展）
_WEB_WHITELIST = (
    ".gov.cn", ".mee.gov.cn", "cnemc.cn", "weather.com.cn", "open-meteo.com",
    "epmap.org", "rmtc.org.cn", "nnsa.mee.gov.cn", "cloud.tencent.com",
)


def _web_fetch(url: str, max_chars: int = 3000) -> str:
    """抓取网页正文（简化版 reader）：HTTP GET → 标题 + 正文纯文本。"""
    import re
    import ssl
    import urllib.request

    if not url.startswith(("http://", "https://")):
        return json.dumps({"error": "URL 必须以 http(s):// 开头"}, ensure_ascii=False)
    # 白名单检查（可用 ECO_WEB_ALLOW_ALL=1 放开）
    import os
    if os.environ.get("ECO_WEB_ALLOW_ALL", "0") != "1":
        host = (urllib.parse.urlparse(url).hostname or "").lower()  # hostname 不含端口
        if not any(host.endswith(w) for w in _WEB_WHITELIST):
            return json.dumps({
                "error": f"域名 {host} 不在政务白名单（{', '.join(_WEB_WHITELIST[:6])}…）；"
                         "如确需访问请由管理员放开 ECO_WEB_ALLOW_ALL"}, ensure_ascii=False)
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (eco-agent web_fetch)"})
        with urllib.request.urlopen(req, context=ctx, timeout=20) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        title = re.search(r"<title[^>]*>([^<]*)</title>", raw, re.I)
        # 去标签取正文
        body = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", "", raw)
        text = re.sub(r"<[^>]+>", " ", body)
        text = re.sub(r"\s+", " ", text).strip()
        return json.dumps({
            "title": title.group(1).strip() if title else "",
            "text": text[:max_chars],
            "truncated": len(text) > max_chars,
            "chars": len(text),
        }, ensure_ascii=False)
    except Exception as e:  # noqa: BLE001
        return json.dumps({"error": f"抓取失败: {e}"}, ensure_ascii=False)


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
    if name == "execute_code":
        # 沙箱代码执行——经 L1-L4 权限闸门（L3：非白名单拒绝并返回原因）
        from agent_core.tools_registry import execute_tool

        result = await execute_tool("execute_code", {
            "code": arguments.get("code", ""),
            "language": arguments.get("language", "python"),
        })
        return result[:2000]
    if name == "web_fetch":
        return _web_fetch(str(arguments.get("url", "")))
    if name == "generate_pptx":
        # PPT 真实文件生成（docgen 插件能力，L2 本地写入）
        # 惰性确保插件已加载（server 不预载插件；首次调用时注册 handler）
        from agent_core.plugins import get_plugin_manager
        from agent_core.tools_registry import execute_tool

        pm = get_plugin_manager()
        if "docgen" not in [p["name"] for p in pm.scan() if p["name"] == "docgen"]:
            return "docgen 插件不存在（plugins/docgen）"
        if pm.get("docgen") is not None and pm.get("docgen").get("status") != "loaded" or pm.get("docgen") is None:
            pm.load("docgen")
        result = await execute_tool("generate_pptx", {
            "slides": arguments.get("slides", []),
            "title": arguments.get("title", "未命名"),
            "filename": arguments.get("filename", ""),
        })
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
        reply, trace, usage, first_llm_ms, first_token_ms = await _chat_with_codex_loop(
            client, messages, req.model)
    except Exception as e:  # noqa: BLE001 — API 边界兜底
        logger.exception("chat failed")
        _persist_turn(req.session_id, req.message, "", ok=False)
        return ChatResponse(reply=f"[eco-server] 对话失败: {e}", model=req.model or "default", usage={})
    _persist_turn(req.session_id, req.message, reply, ok=True)
    duration_ms = int((time.monotonic() - t0) * 1000)
    # 轨迹审计入链（govmcp SM3，五要素）
    try:
        from agent_core.trace_audit import get_trace_audit

        get_trace_audit().record_trace(req.message, reply, len(trace), duration_ms,
                                       model=req.model or client._provider["default_model"])
    except Exception as e:  # noqa: BLE001 — 审计失败不阻断业务
        logger.warning("trace audit failed: %s", e)
    # 教训自动沉淀（自愈闭环：失败对话提炼为 lesson，下次自动注入）
    try:
        from agent_core.lessons import extract_lesson, get_lesson_store

        tool_names = [t.get("name", "") for t in trace if t.get("type") == "tool"]
        lesson = extract_lesson(req.message, reply, tool_names)
        if lesson:
            get_lesson_store().add(lesson)
            logger.info("lesson 已沉淀: %s", lesson.get("lesson", "")[:80])
    except Exception as e:  # noqa: BLE001
        logger.warning("lesson extract failed: %s", e)
    # 会话级 token 计量 + 首个 LLM 响应耗时（非流式下为近似首响应，非逐 token 采样）
    return ChatResponse(reply=reply, model=req.model or "default", usage=usage,
                        duration_ms=duration_ms,
                        ttft_ms=(first_token_ms if first_token_ms is not None else first_llm_ms) or 0,
                        trace=trace)


async def _chat_with_codex_loop(client, messages: list[dict], model: str = "",
                                max_rounds: int = 3, on_event=None,
                                stream_answer: bool = False) -> tuple:
    """法典工具循环：LLM 决定查条 → 执行检索 → 结果回填 → 综合回答。

    返回 (reply, trace, usage, first_llm_ms, first_token_ms)：
    trace 为 DSH 式执行轨迹（思考轮/工具调用/耗时），供 Web UI 折叠展示与 trace_audit 审计入链；
    usage 为本轮对话累加的 token 计量（会话级，非全局）；first_llm_ms 为首个 LLM 响应耗时；
    first_token_ms 为总结回答的首 token 精确采样（仅 stream_answer=True 时非 None）。

    on_event: 可选同步回调（参数为轨迹事件 dict），每步事件实时推送（stream 端点用）；
    stream_answer: True 时总结回答走真实 SSE 流式调用，delta 经 on_event({"type":"delta","text":...}) 推送。

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
    total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    first_llm_ms: int | None = None
    first_token_ms: int | None = None
    empty_talk_re = re.compile(
        r"正在(调用|查询|检索|获取|调取)|请稍候|稍等|马上(为您)?(查询|检索)|我先(查|检索)"
        r"|待工具返回|待.*填入|（此处待|占位）|<invoke|invoke name|kb_get_document|让我直接"
    )

    def _emit(ev: dict) -> None:
        """轨迹事件入链 + 可选实时推送（stream 端点用）。"""
        trace.append(ev)
        if on_event is not None:
            try:
                on_event(ev)
            except Exception:  # noqa: BLE001 — 推送失败不影响主流程
                pass

    def _push_delta(text: str, reset: bool = False) -> None:
        """流式增量推送：只推不记 trace（避免轨迹被逐字块淹没）。"""
        if on_event is not None:
            try:
                ev = {"type": "delta", "text": text}
                if reset:
                    ev["reset"] = True
                on_event(ev)
            except Exception:  # noqa: BLE001
                pass
    round_idx = 0
    for _ in range(max_rounds):
        round_idx += 1
        loop = asyncio.get_event_loop()
        t_llm = time.monotonic()
        round_content_parts: list[str] = []
        if stream_answer:
            # 每轮 LLM 调用走真实流式：content 增量实时推送。
            # 若本轮最终带 tool_calls，已推文字是本轮思考 → 用 reset 撤销；
            # 若本轮直接给出最终回答，delta 即最终答案（首 token 精确采样）。
            def _chunk_round(text: str):
                nonlocal first_token_ms
                if first_token_ms is None:
                    first_token_ms = int((time.monotonic() - t_llm) * 1000)
                round_content_parts.append(text)
                _push_delta(text)

            msg, err = await loop.run_in_executor(
                None, lambda: client._call_chat_with_tools_stream(
                    model or client._provider["default_model"], messages, tools,
                    on_chunk=_chunk_round))
            if err is not None or msg is None:
                # 流式失败回退非流式（统一走下方重试链）
                msg, err = await loop.run_in_executor(
                    None, lambda: client._call_chat_with_tools(
                        model or client._provider["default_model"], messages, tools))
        else:
            msg, err = await loop.run_in_executor(
                None, lambda: client._call_chat_with_tools(model or client._provider["default_model"],
                                                           messages, tools))
        if err or msg is None:
            # 瞬时故障（read timeout 等）先重试一次（非流式）
            _emit({"type": "correction", "round": round_idx, "note": f"LLM瞬时故障重试: {err}"})
            await asyncio.sleep(1.5)
            t_llm = time.monotonic()
            msg, err = await loop.run_in_executor(
                None, lambda: client._call_chat_with_tools(
                    model or client._provider["default_model"], messages, tools))
        llm_ms = int((time.monotonic() - t_llm) * 1000)
        if err or msg is None:
            return f"[eco-server] LLM 调用失败: {err}", trace, total_usage, first_llm_ms, first_token_ms
        if first_llm_ms is None:
            first_llm_ms = llm_ms
        if isinstance(msg, dict):
            u = msg.pop("_usage", None)  # 会话级 token 计量（不下发模型）
            if isinstance(u, dict):
                for k in total_usage:
                    total_usage[k] += int(u.get(k) or 0)
        audit.record_llm_call(model or client._provider["default_model"],
                              round_idx, llm_ms)
        tool_calls = msg.get("tool_calls")
        if tool_calls and stream_answer and round_content_parts:
            # 已实时推送的文字是本轮思考（非最终回答）→ reset 撤销
            _push_delta("", reset=True)
        if not tool_calls:
            content = str(msg.get("content") or "")
            # 空话检测：提及调用工具但未真调用 → 纠偏重试
            if empty_talk_re.search(content):
                if stream_answer:
                    _push_delta("", reset=True)  # 撤销已推的空话
                _emit({"type": "correction", "round": round_idx,
                       "note": "空话纠偏", "cost_ms": llm_ms})
                messages.append({"role": "assistant", "content": content})
                messages.append({
                    "role": "user",
                    "content": "你刚才没有实际调用工具，只输出了预告文字。"
                               "请直接调用 statute_lookup 或 statute_search 获取条文原文，"
                               "基于工具返回的真实结果回答，不要再输出预告。",
                })
                continue
            _emit({"type": "answer", "round": round_idx, "cost_ms": llm_ms,
                   "chars": len(content)})
            if stream_answer and content and not round_content_parts:
                # 流式失败回退非流式成功：切片回放
                if first_token_ms is None:
                    first_token_ms = llm_ms
                for i in range(0, len(content), 6):
                    _push_delta(content[i:i + 6])
                    await asyncio.sleep(0.02)
            return content, trace, total_usage, first_llm_ms, first_token_ms
        _emit({"type": "think", "round": round_idx, "cost_ms": llm_ms,
               "tools": [tc["function"]["name"] for tc in tool_calls],
               "thought": (str(msg.get("content") or "")[:400])})
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
            # 轨迹事件（UI 展示，stream 模式下实时推送）
            _emit({"type": "tool", "round": round_idx, "name": name,
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
    t_llm = time.monotonic()
    content = ""
    stream_ok = False
    if stream_answer:
        # 总结回答走真实 SSE 流式：delta 即时推送（on_event 为线程安全队列，工作线程直接入队）
        _delta_put_n = 0  # noqa: F841 — 占位防误删
        content_parts: list[str] = []

        def _chunk(text: str):
            nonlocal first_token_ms
            if first_token_ms is None:
                first_token_ms = int((time.monotonic() - t_llm) * 1000)
            content_parts.append(text)
            # 工作线程直接入队（on_event 是线程安全队列）；delta 只推送不进 trace
            _push_delta(text)

        msg, err = await loop.run_in_executor(
            None, lambda: client._call_chat_with_tools_stream(
                model or client._provider["default_model"], messages, [], on_chunk=_chunk))
        if err is None and msg is not None:
            stream_ok = True
            content = "".join(content_parts)
        else:
            _emit({"type": "correction", "round": round_idx,
                   "note": f"流式总结失败回退非流式: {err}"})
    if not stream_answer or not stream_ok:
        # 非流式总结（含流式失败回退）
        msg, err = await loop.run_in_executor(
            None, lambda: client._call_chat_with_tools(model or client._provider["default_model"],
                                                       messages, []))
        if err or msg is None:
            # 瞬时故障（read timeout 等）先重试一次
            _emit({"type": "correction", "round": round_idx, "note": f"总结调用瞬时故障重试: {err}"})
            await asyncio.sleep(1.5)
            t_llm = time.monotonic()
            msg, err = await loop.run_in_executor(
                None, lambda: client._call_chat_with_tools(
                    model or client._provider["default_model"], messages, []))
        llm_ms = int((time.monotonic() - t_llm) * 1000)
        if err or msg is None:
            return f"[eco-server] LLM 调用失败: {err}", trace, total_usage, first_llm_ms, first_token_ms
        if first_llm_ms is None:
            first_llm_ms = llm_ms
        if first_token_ms is None:
            first_token_ms = llm_ms
        if isinstance(msg, dict):
            u = msg.pop("_usage", None)  # 会话级 token 计量（不下发模型）
            if isinstance(u, dict):
                for k in total_usage:
                    total_usage[k] += int(u.get(k) or 0)
        content = str(msg.get("content") or "")
    else:
        # 流式成功：usage 随消息带回
        llm_ms = int((time.monotonic() - t_llm) * 1000)
        if first_llm_ms is None:
            first_llm_ms = llm_ms
        if isinstance(msg, dict):
            u = msg.pop("_usage", None)
            if isinstance(u, dict):
                for k in total_usage:
                    total_usage[k] += int(u.get(k) or 0)
    # 幻觉兜底：仍输出工具调用格式（含全角变体）→ 最强约束重试一次
    if "tool_calls" in content or "invoke" in content:
        _emit({"type": "correction", "round": round_idx, "note": "幻觉格式纠偏"})
        messages.append({"role": "user",
                         "content": "禁止输出 tool_calls、invoke 等任何工具调用格式（含全角符号），"
                                    "现在只输出给用户的最终文字回答。"})
        msg2, err2 = await loop.run_in_executor(
            None, lambda: client._call_chat_with_tools(
                model or client._provider["default_model"], messages, []))
        if err2 is None and msg2 is not None:
            if isinstance(msg2, dict):
                u2 = msg2.pop("_usage", None)
                if isinstance(u2, dict):
                    for k in total_usage:
                        total_usage[k] += int(u2.get(k) or 0)
            content = str(msg2.get("content") or "")
            if stream_answer and content:
                # 流式模式下旧 delta 已推送：reset 重放正确内容
                _push_delta(content, reset=True)
    # 末层兜底：贪婪剥离未闭合的工具调用残留（半角/全角通吃）
    content = re.sub(r"[<＜]tool_calls>[\s\S]*$", "", content).strip()
    content = re.sub(r"[<＜]invoke[\s\S]*$", "", content).strip()
    if stream_answer and content and not stream_ok:
        # 非流式回退/重试结果逐片回放（stream_ok 时 delta 已实时推过）
        for i in range(0, len(content), 6):
            _push_delta(content[i:i + 6])
            await asyncio.sleep(0.02)
    _emit({"type": "answer", "round": round_idx, "chars": len(content)})
    return (content or "[eco-server] 模型未给出有效回答"), trace, total_usage, first_llm_ms, first_token_ms


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
    """流式对话（DSH 式实时事件流）：

    - think/tool/correction 轨迹事件边跑边推（前端过程块实时渲染）；
    - 总结回答走真实 SSE 流式调用，delta 即时推送，首 token 精确采样；
    - 结束时发 done（会话级 usage / duration / ttft / 全量 trace）。
    """
    import asyncio
    import queue
    import time

    from agent_core.llm_client import get_default_client

    client = get_default_client()
    messages = _build_messages(req.message, req.history)
    t0 = time.monotonic()
    # 线程安全队列：工作线程（流式 chunk 回调）与事件循环（gen 消费）共用，
    # 不依赖 call_soon_threadsafe（uvloop/macOS 下该机制有 8s+ 延迟 bug）
    ev_q: queue.Queue = queue.Queue()

    def on_event(ev: dict) -> None:
        ev_q.put_nowait(ev)

    async def gen():
        task = asyncio.create_task(
            _chat_with_codex_loop(client, messages, req.model,
                                  on_event=on_event, stream_answer=True))
        streamed = False
        first_delta_ms: int | None = None  # 首个可见输出距请求开始（DSH 首 token 语义）
        while not task.done() or not ev_q.empty():
            try:
                ev = ev_q.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.05)  # 轮询间隔 50ms，实时性足够
                continue
            if ev.get("type") == "delta":
                if not streamed:
                    first_delta_ms = int((time.monotonic() - t0) * 1000)
                streamed = True
                payload = {"delta": ev.get("text", "")}
                if ev.get("reset"):
                    payload["reset"] = True
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                continue
            # think/tool/correction 轨迹事件实时推送
            yield f"data: {json.dumps({'trace_event': ev}, ensure_ascii=False)}\n\n"
        # 循环结束：取结果收尾
        try:
            reply, trace, usage, first_llm_ms, first_token_ms = task.result()
        except Exception as e:  # noqa: BLE001
            logger.exception("chat_stream failed")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            yield "data: [DONE]\n\n"
            return
        if not streamed:
            # 无流式输出（失败回复等）：整体回放
            for i in range(0, len(reply), 6):
                yield f"data: {json.dumps({'delta': reply[i:i + 6]}, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0.02)
        ttft = first_delta_ms if first_delta_ms is not None else (
            first_token_ms if first_token_ms is not None else first_llm_ms)
        # 会话落盘（重启可恢复）：失败回复（[eco-server] 开头）不写 assistant 消息
        ok = not reply.startswith("[eco-server]")
        _persist_turn(req.session_id, req.message, reply, ok=ok)
        done_payload = json.dumps({"done": True, "usage": usage, "trace": trace,
                                   "ttft_ms": ttft,
                                   "duration_ms": int((time.monotonic() - t0) * 1000)})
        yield f"data: {done_payload}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")
