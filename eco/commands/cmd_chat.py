"""
eco chat — Agent Loop with Tool Calling (CLAUDE/CODEX/HERMES 模式)

流程：
  1. 用户提问
  2. 发送消息 + 100+ 工具定义给 LLM
  3. LLM → 决定调用工具 → 执行 → 继续推理 → 输出回答
  4. 工具调用过程实时显示
"""
import sys, threading, time
from pathlib import Path

_IS_WINDOWS = sys.platform.startswith("win")

import logging
logging.basicConfig(level=logging.WARNING)

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

SYSTEM_PROMPT = """你是 ECO AGENT，生态环境法规领域的 AI 助手。

## 你的能力
- 精通中国生态环境法律法规
- 可以调用 100+ 政务工具查询数据、法规、标准
- 拥有 36 个生态环境专业技能
- 能进行多法规交叉分析、场景推演、风险评估

## 使用工具
当用户的问题需要查询数据或法规条款时，务必调用你的工具来获取准确信息。
不要凭记忆编造具体数据。

## 回答风格
- 引用法规时标注具体条款号
- 涉及处罚标注「本回答仅供参考，不构成法律意见」
- 结构化、清晰、专业
"""

def _build_messages(history, question):
    system = SYSTEM_PROMPT + f"\n\n你有工具可以查询法规、标准、监测数据等。在回答中可以使用标记来引用工具调用结果。"
    messages = [{"role": "system", "content": system}]
    for h in history[-10:]:
        messages.append(h)
    messages.append({"role": "user", "content": question})
    return messages


def _stream_answer(messages):
    """
    L1 ReAct++ 循环（真实 LLM 推理 + 工具调用）：
    1. 显示思考指示器
    2. ReActPlusPlus.execute() → LLM think → decide → act → observe
    3. 流式输出最终回答
    """
    from agent_core.react_loop import ReActPlusPlus
    from agent_core.llm_client import get_default_client
    from agent_core.tools_registry import get_tools

    # 检查 LLM 可用
    c = get_default_client()
    if not c.available():
        msg = "[LLM not configured. Run: eco setup]"
        print(msg)
        return msg

    # 提取用户问题
    user_query = ""
    for m in reversed(messages):
        if m["role"] == "user":
            user_query = m["content"]
            break
    if not user_query:
        user_query = messages[-1]["content"] if messages else ""

    full_text = [""]
    first_chunk_received = [False]
    stop_animation = [False]

    def animate():
        sys.stdout.write("  -- 思考中")
        sys.stdout.flush()
        while not stop_animation[0]:
            for dots in range(1, 4):
                if stop_animation[0]:
                    break
                sys.stdout.write("\r  -- 思考中" + "." * dots + " " * (3 - dots))
                sys.stdout.flush()
                time.sleep(0.3)
                if first_chunk_received[0]:
                    return

    anim = threading.Thread(target=animate, daemon=True)
    anim.start()
    time.sleep(0.05)

    # 构建 ReAct++ 实例，注册工具
    loop = ReActPlusPlus()
    tools = get_tools()
    for t in tools:
        fn = t["function"]
        name = fn["name"]
        desc = fn["description"]
        from agent_core.tools_registry import execute_tool
        import asyncio
        def make_handler(tool_name):
            def handler(**kwargs):
                try:
                    # ReAct++ passes {"query": "用户问题"}, map to tool params
                    args = dict(kwargs)
                    if "query" in args and args["query"]:
                        args["keyword"] = args["query"]
                        args["city"] = args["query"][:20]
                        args["company_name"] = args["query"][:20]
                    result = asyncio.run(execute_tool(tool_name, args))
                    return result
                except Exception as e:
                    return f"[工具执行错误: {e}]"
            return handler
        loop.register_tool(name, make_handler(name), desc)

    # 执行 ReAct++ 循环
    result = loop.execute(user_query)
    stop_animation[0] = True

    # 清理指示器
    if not first_chunk_received[0]:
        sys.stdout.write("\r" + " " * 40 + "\r")

    # 构建输出
    output = ""
    if isinstance(result, dict):
        obs = result.get("final_observation", "")
        if obs and obs != "任务完成":
            output = obs
        else:
            thought = result.get("thought", "")
            if thought:
                output = thought
            else:
                output = f"任务完成 (共{result['steps']}步，置信度{result['confidence']:.2f})"

    display = output.replace("**", "") if _IS_WINDOWS else output
    sys.stdout.write(display)
    sys.stdout.write("\n")
    sys.stdout.flush()

    full_text[0] = output
    return output


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
        print("\n  ECO AGENT -- 生态环境法规 AI 助手")
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

        print()
        messages = _build_messages(history, q)
        answer = _stream_answer(messages)

        history.append({"role": "user", "content": q})
        history.append({"role": "assistant", "content": answer})
        if len(history) > 100:
            history = history[-50:]

    return 0
