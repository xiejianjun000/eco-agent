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

def _build_messages(history, question):
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for h in history[-10:]:
        messages.append(h)
    messages.append({"role": "user", "content": question})
    return messages

def _safe(text):
    """Filter non-BMP characters for Windows terminal"""
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
        messages = _build_messages([], args.query)
        _stream_answer(messages)
        return 0
    return _repl()

LOGO = r"""
      ╱▔▔╲      ╱▔▔╲
     ╱  ╲ ═    ╱  ╲
    ╱  /\  ╲  ╱  /\  ╲
    ▕  \/  ▏  ▕  \/  ▏
      ╰╥╯      ╰╥╯
       ║        ║

   ███████╗ ██████╗ ██████╗     █████╗  ██████╗ ███████╗███╗  ██╗████████╗
   ██╔════╝██╔═══██╗██╔══██╗   ██╔══██╗██╔════╝ ██╔════╝████╗ ██║╚══██╔══╝
   █████╗  ██║   ██║██████╔╝   ███████║██║  ███╗█████╗  ██╔██╗██║   ██║
   ██╔══╝  ██║   ██║██╔══██╗   ██╔══██║██║   ██║██╔══╝  ██║╚████║   ██║
   ███████╗╚██████╔╝██║  ██║   ██║  ██║╚██████╔╝███████╗██║ ╚███║   ██║
   ╚══════╝ ╚═════╝ ╚═╝  ╚═╝   ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚══╝   ╚═╝

                     大气带律师  ·  生态环境法规 AI 助手
"""

def _repl():
    history = []
    if _HAVE_RICH:
        from rich.text import Text
        _console.print()
        _console.print(Text(LOGO, style="#3a8a6f"))
        _console.print(Text("  /exit  /new  /help  |  ECO AGENT v5.0.0a2", style="#2a5a3a"))
        _console.print()
    else:
        print(LOGO)
        print("  (/exit /new /help)\n")

    while True:
        try:
            q = input("eco> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not q: continue
        if q in ("/exit", "/quit"): break
        if q == "/help":
            print("  /exit  /new"); continue
        if q == "/new":
            history = []; print("[重置]"); continue

        messages = _build_messages(history, q)
        answer = _stream_answer(messages)
        print()

        history.append({"role": "user", "content": q})
        history.append({"role": "assistant", "content": answer})
        if len(history) > 100:
            history = history[-50:]

    return 0
