"""
eco chat — Windows 友好的终端输出

设计原则：
  - 所有字符 GBK 兼容（不出现 ○ · ● 等特殊符号）
  - 流式输出不做 rich markup 渲染（Windows 终端 ANSI 支持差）
  - 输出完成后再用 rich Markdown 渲染最终版
  - 干净、不重复、可读
"""
import sys, os, threading, time
from pathlib import Path

_IS_WINDOWS = sys.platform.startswith("win")

import logging
logging.basicConfig(level=logging.WARNING)
log = logging.getLogger("eco.chat")
ROOT = Path(__file__).resolve().parent.parent.parent

try:
    from rich.console import Console
    from rich.panel import Panel
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
    两段式输出：
    1. 思考指示器 → 流式正文（纯文本追加）
    2. 流式完成 → rich Markdown 渲染最终版（Windows 下跳过）
    """
    from agent_core.llm_client import get_default_client
    c = get_default_client()
    if not c.available():
        msg = "[LLM not configured. Run: eco setup]"
        print(msg)
        return msg

    full_text = [""]
    first_chunk_received = [False]
    stop_animation = [False]

    # ── 动画线程 ──
    def animate():
        try:
            sys.stdout.write("  -- 思考中")
            sys.stdout.flush()
            first_chunk_received[0]  # ref
            dots = 0
            while not stop_animation[0]:
                dots = (dots + 1) % 4
                sys.stdout.write("\r  -- 思考中" + "." * dots + " " * (3 - dots))
                sys.stdout.flush()
                time.sleep(0.3)
                if first_chunk_received[0]:
                    break
        except:
            pass

    anim = threading.Thread(target=animate, daemon=True)
    anim.start()
    time.sleep(0.05)

    # ── 流式输出回调 ──
    def on_chunk(chunk):
        if not first_chunk_received[0]:
            first_chunk_received[0] = True
            sys.stdout.write("\r" + " " * 40 + "\r")
            sys.stdout.flush()
        full_text[0] += chunk
        # Windows 下去掉 ** 标记，显示纯文本
        if _IS_WINDOWS:
            display = chunk.replace("**", "")
            sys.stdout.write(display)
        else:
            sys.stdout.write(chunk)
        sys.stdout.flush()

    # ── 发起流式请求 ──
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
        _console.print(Panel("[bold]ECO AGENT[/bold]  --  生态环境法规 AI 助手", box=box.ROUNDED))
        _console.print("  [dim]/exit  /new  /help[/dim]")
        _console.print()
    else:
        print()
        print("  ECO AGENT -- 生态环境法规 AI 助手")
        print("  (/exit /new /help)")
        print()

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

        print()
        messages = _build_messages(history, q)
        answer = _stream_answer(messages)

        history.append({"role": "user", "content": q})
        history.append({"role": "assistant", "content": answer})
        if len(history) > 100:
            history = history[-50:]

    return 0
