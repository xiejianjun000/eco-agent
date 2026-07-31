"""
eco chat - CLAUDE/CODEX/HERMES pattern
  LLM <-> Tools -> Final answer
"""
import sys, threading, time
from pathlib import Path

_IS_WINDOWS = sys.platform.startswith("win")
import logging
logging.basicConfig(level=logging.WARNING)

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich import box
    _console = Console()
    _HAVE_RICH = True
except ImportError:
    _console = None
    _HAVE_RICH = False

SYSTEM_PROMPT = "你是 ECO AGENT，生态环境法规领域的 AI 助手。精通中国生态环境法律法规。可以调用 100+ 政务工具。引用法规时标注具体条款号。涉及处罚标注免责声明。用中文回答。"

LOGO = r"""
   ███████╗ ██████╗ ██████╗     █████╗  ██████╗ ███████╗███╗  ██╗████████╗
   ██╔════╝██╔═══██╗██╔══██╗   ██╔══██╗██╔════╝ ██╔════╝████╗ ██║╚══██╔══╝
   █████╗  ██║   ██║██████╔╝   ███████║██║  ███╗█████╗  ██╔██╗██║   ██║
   ██╔══╝  ██║   ██║██╔══██╗   ██╔══██║██║   ██║██╔══╝  ██║╚████║   ██║
   ███████╗╚██████╔╝██║  ██║   ██║  ██║╚██████╔╝███████╗██║ ╚███║   ██║
   ╚══════╝ ╚═════╝ ╚═╝  ╚═╝   ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚══╝   ╚═╝
"""

LOGO_LINE = "  ECO AGENT  --  da qi dai lv shi  --  Environmental Regulation AI"

def _build_messages(history, question, system_extra=""):
    system = SYSTEM_PROMPT
    if system_extra:
        system = system + "\n\n" + system_extra
    messages = [{"role": "system", "content": system}]
    for h in history[-10:]:
        messages.append(h)
    messages.append({"role": "user", "content": question})
    return messages

def _workspace_system_extra(query: str = ""):
    """当前工作区内容（有 query 时按相关性混合检索片段，否则摘要）经 prompt_engine
    注入校验后进入动态层，返回拼接进 system 的文本"""
    from agent_core.workspace import get_workspace_manager
    mgr = get_workspace_manager()
    if mgr.current() is None:
        return ""
    if mgr.inject_current_summary(query=query):
        from agent_core.prompt_engine import get_prompt_engine
        return get_prompt_engine().build_system_prompt()
    return ""

def _handle_resume_intent(q):
    """跨会话续接：识别"继续上次XX的检查"类意图，自动匹配并加载工作区"""
    from agent_core.workspace import get_workspace_manager
    mgr = get_workspace_manager()
    if mgr.current() is not None:
        return None
    ws = mgr.detect_resume_intent(q)
    if ws is not None:
        mgr.open(ws.meta.get("slug", ws.path.name))
        print(f"[workspace] 已自动加载工作区: {ws.meta.get('name')}（历史事件 {len(ws.history())} 条）")
        return ws
    return None

def _maybe_swarm(q, context=""):
    """复杂执法任务启用三角色协作；简单问答返回 None"""
    from agent_core.role_swarm import get_role_swarm, is_complex_task
    if not is_complex_task(q):
        return None
    swarm = get_role_swarm()
    result = swarm.run(q, context=context)
    print(swarm.format_result(result))
    return result["synthesis"] or "\n".join(
        f"[{r}] {t}" for r, t in result["contributions"].items())

def _safe(text):
    if _IS_WINDOWS:
        try:
            text.encode(sys.stdout.encoding)
            return text
        except:
            return ''.join(c for c in text if ord(c) < 65536)
    return text

def _stream_answer(messages):
    from agent_core.llm_client import get_default_client
    from agent_core.tools_registry import get_tools
    c = get_default_client()
    if not c.available():
        print("[LLM not configured. Run: eco setup]")
        return ""
    full_text = [""]
    first_chunk_received = [False]
    def on_chunk(chunk):
        if not first_chunk_received[0]:
            first_chunk_received[0] = True
        full_text[0] += chunk
        display = _safe(chunk)
        sys.stdout.write(display)
        sys.stdout.flush()
    tools = get_tools()
    result = c.chat_with_tools(messages, tools=tools, on_chunk=on_chunk, max_tool_rounds=5)
    return result

def run(args):
    if args.query:
        _handle_resume_intent(args.query)
        extra = _workspace_system_extra(args.query)
        messages = _build_messages([], args.query, system_extra=extra)
        _stream_answer(messages)
        return 0
    return _repl()

def _repl():
    history = []
    if _HAVE_RICH:
        from rich.text import Text
        _console.print()
        _console.print(Text(LOGO, style="#3a8a6f"))
        _console.print(Text(LOGO_LINE, style="#5ae0a0 bold"))
        _console.print(Text("  /exit  /new  /help  |  ECO AGENT v5.0.0a2", style="#2a5a3a"))
        _console.print()
    else:
        print(LOGO)
        print(LOGO_LINE)
        print("  (/exit /new /help)")
        print()

    from agent_core.workspace import get_workspace_manager
    mgr = get_workspace_manager()
    while True:
        try:
            cur = mgr.current_name()
            prompt_str = f"eco[{cur}]> " if cur else "eco> "
            q = input(prompt_str).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not q: continue
        if q in ("/exit", "/quit"): break
        if q == "/help":
            print("  /exit  /new  /ws"); continue
        if q == "/new":
            history = []; print("[reset]"); continue
        if q == "/ws":
            cur = mgr.current()
            print(mgr.current().summary() if cur else "[workspace] 当前无打开的工作区")
            continue

        _handle_resume_intent(q)
        ws = mgr.current()
        context = ws.summary() if ws else ""
        extra = _workspace_system_extra(q)

        answer = _maybe_swarm(q, context=context)
        if answer is None:
            messages = _build_messages(history, q, system_extra=extra)
            answer = _stream_answer(messages)
        print()

        history.append({"role": "user", "content": q})
        history.append({"role": "assistant", "content": answer})
        if len(history) > 100:
            history = history[-50:]
        if ws:
            ws.add_event("user", q)
            ws.add_event("assistant", answer[:800])
    return 0
