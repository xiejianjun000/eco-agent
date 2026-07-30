"""
eco chat — CLAUDE Code 风格终端输出

设计：
  1. ○ 思考指示器（输出前显示，用户可见）
  2. 打字机流式输出（rich.render.Style 逐段着色）
  3. 无重复、无闪烁、无二次渲染
"""
import sys, logging, threading, time
from pathlib import Path

logging.basicConfig(level=logging.WARNING)
log = logging.getLogger("eco.chat")
ROOT = Path(__file__).resolve().parent.parent.parent

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.markdown import Markdown
    from rich.style import Style
    from rich.text import Text
    from rich import box
    _console = Console()
    _HAVE_RICH = True
except ImportError:
    _console = None
    _HAVE_RICH = False

SYSTEM_PROMPT = """## 你是谁
你是 ECO AGENT，生态环境法规领域的 AI 助手，专注中国环境法律体系。

## 你的能力
- 精通中国生态环境法律法规
- 可以调用 100+ 政务工具
- 拥有 36 个生态环境专业技能
- 能进行多法规交叉分析、场景推演、风险评估

## 风格
- 用中文回答。专业、精准、结构化。
- 引用法规时标注具体条款号。
- 涉及处罚的内容标注「本回答仅供参考，不构成法律意见」。
- 回答中使用 **加粗** 突出关键词。
"""

def _build_messages(history, question):
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for h in history[-10:]:
        messages.append(h)
    messages.append({"role": "user", "content": question})
    return messages


def _stream_answer(messages):
    """
    CLAUDE Code 风格三阶段：
    1. 显示 ○ 思考中（用户可见）
    2. 流式输出（rich 实时渲染）
    3. 空行结束
    """
    from agent_core.llm_client import get_default_client
    c = get_default_client()
    if not c.available():
        msg = "[LLM not configured. Run: eco setup]"
        print(msg)
        return msg

    full_text = [""]
    first_chunk_received = [False]
    animation_started = [False]

    def on_chunk(chunk):
        if not first_chunk_received[0]:
            first_chunk_received[0] = True
            sys.stdout.write("\r" + " " * 40 + "\r")
            sys.stdout.flush()
        full_text[0] += chunk
        if _HAVE_RICH:
            _console.out(chunk, end="")
        else:
            sys.stdout.write(chunk)
        sys.stdout.flush()

    # 阶段一：显示思考指示器（优先启动动画，再发起请求）
    stop_animation = [False]

    def animate():
        dots = 0
        # 先显示一次，确保用户看到
        sys.stdout.write("\r  ○ 思考中")
        sys.stdout.flush()
        animation_started[0] = True
        while not stop_animation[0] and not first_chunk_received[0]:
            dots = (dots + 1) % 4
            sys.stdout.write("\r  ○ 思考中" + "·" * dots + " " * (3 - dots))
            sys.stdout.flush()
            time.sleep(0.25)

    # 启动动画线程
    anim = threading.Thread(target=animate, daemon=True)
    anim.start()

    # 等待动画线程至少显示一次再发起请求
    time.sleep(0.05)

    # 阶段二：流式输出
    c.chat_stream(messages, on_chunk=on_chunk)
    stop_animation[0] = True

    # 清除残留指示器
    if not first_chunk_received[0]:
        sys.stdout.write("\r" + " " * 40 + "\r")

    sys.stdout.write("\n")
    sys.stdout.flush()
    return full_text[0]


def run(args):
    if args.query:
        messages = _build_messages([], args.query)
        _stream_answer(messages)
        return 0
    return _repl()


def _repl():
    history = []
    if _HAVE_RICH:
        _console.print()
        _console.print(Panel("[bold]ECO AGENT[/bold]  —  生态环境法规 AI 助手", box=box.ROUNDED))
        _console.print("  [dim]/exit[bold]/[/bold]/new[bold]/[/bold]/help[/dim]")
        _console.print()
    else:
        print("\n  ECO AGENT — 生态环境法规 AI 助手")
        print("  (/exit /new /help)\n")

    while True:
        try:
            q = input("eco> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not q:
            continue
        if q in ("/exit", "/quit"):
            break
        if q == "/help":
            print("  /exit  /new")
            continue
        if q == "/new":
            history = []
            print("[对话已重置]")
            continue

        messages = _build_messages(history, q)
        answer = _stream_answer(messages)

        history.append({"role": "user", "content": q})
        history.append({"role": "assistant", "content": answer})
        if len(history) > 100:
            history = history[-50:]

    return 0
