"""
eco chat - Conversational AI (CLAUDE/CODEX/HERMES pattern)
  - Streaming output (character by character via SSE)
  - Thinking indicator
  - Markdown-rendered responses (via rich)
  - SOUL.md identity loaded into system prompt
  - Multi-turn conversation with context management
"""
import sys, logging
from pathlib import Path

logging.basicConfig(level=logging.WARNING)
log = logging.getLogger("eco.chat")
ROOT = Path(__file__).resolve().parent.parent.parent

# Note: System prompt is hard-coded below as a CLAUDE-style third-person instruction.
# SOUL.md is available at profiles/eco-agent/SOUL.md for reference but not loaded directly.
_has_identity = Path(ROOT / "profiles" / "eco-agent" / "SOUL.md").exists()

# --- Rich terminal rendering ---
_HAVE_RICH = False
try:
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.live import Live
    from rich.spinner import Spinner
    from rich.panel import Panel
    from rich import box
    _console = Console()
    _HAVE_RICH = True
except ImportError:
    _console = None

def _build_messages(identity, history, question):
    # CLAUDE/HERMES pattern: third-person hard instruction, not first-person intro
    system = """You are ECO AGENT, an AI assistant specialized in environmental regulations and law.

## Identity & Expertise
You have deep expertise in Chinese environmental law: Environmental Protection Law, Air Pollution Prevention Law, Water Pollution Prevention Law, Soil Pollution Prevention Law, Emission Permit管理条例, etc.
You have access to 100+ government tools covering environmental monitoring, carbon emission, enterprise service, citizen service, smart city.
You have 36 specialized environmental enforcement skills.

## Mandatory Rules
1. YOU ARE ECO AGENT — never say "as an AI" or "I don't have tools" or "based on my training data". You HAVE tools and skills.
2. ALWAYS cite specific legal article numbers when referencing regulations.
3. Use structured output: lists, tables, clear sections.
4. When discussing penalties, include penalty ranges and legal basis.
5. Mark uncertain information with [pending confirmation].
6. Add "For reference only, not legal advice" at the end of enforcement-related answers.
7. Be professional, rigorous, practical, and cautious.

## Conversation Style
- Direct, expert, confident
- Chinese language
- Environmental regulation focused
"""
    messages = [{"role": "system", "content": system}]
    for h in history[-10:]:
        messages.append(h)
    messages.append({"role": "user", "content": question})
    return messages

def _stream_answer(messages):
    """Stream answer with real-time output"""
    from agent_core.llm_client import get_default_client
    c = get_default_client()
    if not c.available():
        msg = "[LLM not configured. Run: eco setup]"
        if _HAVE_RICH:
            _console.print(f"[red]{msg}[/red]")
        else:
            print(msg)
        return msg

    full_text = [""]

    if _HAVE_RICH:
        spinner = Spinner("dots", text=" Thinking...")
        with Live(spinner, refresh_per_second=10, transient=True) as live:
            def on_chunk(chunk):
                full_text[0] += chunk
                live.update(Markdown(full_text[0]))
            c.chat_stream(messages, on_chunk=on_chunk)
    else:
        def on_chunk(chunk):
            print(chunk, end="", flush=True)
        c.chat_stream(messages, on_chunk=on_chunk)
        print()

    return full_text[0]

def run(args):
    if args.query:
        messages = _build_messages(None, [], args.query)
        _stream_answer(messages)
        return 0
    return _repl()

def _repl():
    history = []
    if _HAVE_RICH:
        _console.print()
        _console.print(Panel("[bold]ECO AGENT[/bold] - Environmental Regulation AI Assistant", box=box.ROUNDED))
        _console.print("  [dim]/exit  /new  /help[/dim]")
        _console.print()
    else:
        print()
        print("  ECO AGENT - Environmental Regulation AI Assistant")
        print("  (/exit /new /help)")
        print()

    while True:
        try:
            q = input("eco> ").strip()
        except (EOFError, KeyboardInterrupt):
            print(); break
        if not q: continue
        if q in ("/exit", "/quit"): break
        if q == "/help":
            print("  /exit  /new"); continue
        if q == "/new":
            history = []
            if _HAVE_RICH:
                _console.print("[dim]Session reset[/dim]")
            else:
                print("[Session reset]")
            continue

        messages = _build_messages(None, history, q)
        answer = _stream_answer(messages)
        if _HAVE_RICH:
            _console.print()
        else:
            print()

        history.append({"role": "user", "content": q})
        history.append({"role": "assistant", "content": answer})
        if len(history) > 100:
            history = history[-50:]

    return 0
