"""
eco chat — CLAUDE Code 风格终端输出

设计：
  1. ○ 思考指示器（单行动画，自动消失）
  2. 打字机流式输出（rich markup 实时渲染）
  3. 无重复、无闪烁、无二次渲染
"""
import sys, logging, threading, time
from pathlib import Path

logging.basicConfig(level=logging.WARNING)
log = logging.getLogger("eco.chat")
ROOT = Path(__file__).resolve().parent.parent.parent

# Rich 用于最终渲染和欢迎面板
try:
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich import box
    _console = Console()
    _HAVE_RICH = True
except ImportError:
    _console = None
    _HAVE_RICH = False

SYSTEM_PROMPT = """## 你是谁
你是 ECO AGENT，生态环境法规领域的 AI 助手。

## 你的能力
- 精通中国生态环境法律法规：环境保护法、大气污染防治法、水污染防治法、土壤污染防治法、排污许可管理条例等
- 可以调用 100+ 政务工具（环境监测、碳排放、企业服务、市民服务、智慧城市等）
- 拥有 36 个生态环境专业技能（执法检查、裁量建议、法规检索、标准匹配等）
- 能进行多法规交叉分析、场景推演、风险评估

## 必须遵守的规则
1. 你是 ECO AGENT — 不允许说"作为AI助手"、"我没有工具"、"基于我的训练数据"
2. 引用法规时必须标注具体条款号
3. 涉及处罚的内容必须包含法律依据和处罚幅度
4. 回答结构化：使用列表、表格、分层标题
5. 不确定的内容标注 [待确认]
6. 执法相关内容末尾加注「本回答仅供参考，不构成法律意见」
7. 用中文回答，专业、严谨、务实
"""

def _build_messages(history, question):
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for h in history[-10:]:
        messages.append(h)
    messages.append({"role": "user", "content": question})
    return messages


def _stream_answer(messages):
    """
    CLAUDE Code 风格三阶段输出：
    1. ◉ 思考指示器（直到第一个 chunk）
    2. 打字机输出（追加式）
    3. rich Markdown 渲染最终版
    """
    from agent_core.llm_client import get_default_client
    c = get_default_client()
    if not c.available():
        msg = "[LLM not configured. Run: eco setup]"
        print(msg)
        return msg

    full_text = [""]
    first_chunk_received = [False]

    def on_chunk(chunk):
        if not first_chunk_received[0]:
            # 清除思考指示器行
            sys.stdout.write("\r" + " " * 30 + "\r")
            sys.stdout.flush()
            first_chunk_received[0] = True
        full_text[0] += chunk
        # CLAUDE Code 风格：使用 console.out 实时渲染 markup
        if _HAVE_RICH:
            _console.out(chunk, end="")
        else:
            sys.stdout.write(chunk)
        sys.stdout.flush()

    # 阶段一：显示思考指示器
    sys.stdout.write("  ○  Thinking")
    sys.stdout.flush()

    # 后台运行动画（简单点的点）
    stop_animation = [False]
    def animate():
        dots = 0
        while not stop_animation[0] and not first_chunk_received[0]:
            dots = (dots + 1) % 4
            sys.stdout.write("\r  ○  Thinking" + "." * dots + " " * (3 - dots))
            sys.stdout.flush()
            time.sleep(0.3)

    anim = threading.Thread(target=animate, daemon=True)
    anim.start()

    # 阶段二：流式输出
    c.chat_stream(messages, on_chunk=on_chunk)
    stop_animation[0] = True

    # 阶段三：完成
    sys.stdout.write("\n")

    return full_text[0]


def run(args):
    if args.query:
        messages = _build_messages([], args.query)
        _stream_answer(messages)
        return 0
    return _repl()


def _repl():
    history = []
    # 欢迎面板
    if _HAVE_RICH:
        _console.print()
        _console.print(Panel("[bold]ECO AGENT[/bold]  —  生态环境法规 AI 助手", box=box.ROUNDED))
        _console.print("  [dim]/exit  /new  /help[/dim]")
        _console.print()
    else:
        print("\n  ECO AGENT  —  生态环境法规 AI 助手")
        print("  (/exit  /new  /help)\n")

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
