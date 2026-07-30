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

# --- Load ECO identity from SOUL.md (like CLAUDE loads AGENTS.md) ---
def _load_identity() -> str:
    soul_path = ROOT / "profiles" / "eco-agent" / "SOUL.md"
    if soul_path.exists():
        return soul_path.read_text(encoding="utf-8")
    return "ECO AGENT - environmental regulation AI assistant"

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
    system = identity + """

## Output format
- Cite specific clauses when referencing regulations
- Mark enforcement/penalty info with "For reference only, not legal advice"
- Structured, clear, practical answers
- Mark uncertain items with [pending confirmation]
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
    identity = _load_identity()
    if args.query:
        messages = _build_messages(identity, [], args.query)
        _stream_answer(messages)
        return 0
    return _repl(identity)

def _repl(identity):
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

        messages = _build_messages(identity, history, q)
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
