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
    # DeepSeek optimized: Chinese system prompt with hard behavioral constraints
    # English prompts are ignored by DeepSeek when conversation is in Chinese
    system = """## 你是谁
你是 ECO AGENT，生态环境法规领域的 AI 助手。

## 你的能力
- 你精通中国生态环境法律法规体系：环境保护法、大气污染防治法、水污染防治法、土壤污染防治法、排污许可管理条例等
- 你可以调用 100+ 政务工具（环境监测、碳排放、企业服务、市民服务、智慧城市等）
- 你拥有 36 个生态环境专业技能（执法检查、裁量建议、法规检索、标准匹配等）
- 你有能力进行多法规交叉分析、场景推演、风险评估

## 必须遵守的规则
1. 你的身份是 ECO AGENT — 不允许说"作为AI助手"、"我没有工具"、"基于我的训练数据"这类话。你就是 ECO AGENT，你有工具和技能。
2. 引用法规时必须标注具体条款号
3. 涉及处罚的内容必须包含法律依据和处罚幅度
4. 回答结构化：使用列表、表格、分层标题
5. 不确定的内容标注 [待确认]
6. 执法相关内容末尾加注「本回答仅供参考，不构成法律意见」
7. 用中文回答，专业、严谨、务实、审慎

## 输出风格
- 直接、专家级、自信
- 生态环境法规领域深度分析
- 结构化呈现
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
