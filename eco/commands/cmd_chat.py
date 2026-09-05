"""
eco chat - CLAUDE/CODEX/HERMES pattern
  LLM <-> Tools -> Final answer
"""

import logging
import sys

from eco import __version__

_IS_WINDOWS = sys.platform.startswith("win")

logging.basicConfig(level=logging.WARNING)


try:
    from rich import box  # noqa: F401
    from rich.console import Console
    from rich.panel import Panel  # noqa: F401

    _console = Console()
    _HAVE_RICH = True
except ImportError:
    _console = None
    _HAVE_RICH = False

# DEPRECATED: 单行硬编码提示词已废弃，系统提示词统一由 prompt_engine（SOUL 驱动）产出。
# 保留该常量仅为向后兼容外部引用。

LOGO = r"""
   ███████╗ ██████╗ ██████╗     █████╗  ██████╗ ███████╗███╗  ██╗████████╗
   ██╔════╝██╔════╝██╔═══██╗   ██╔══██╗██╔════╝ ██╔════╝████╗ ██║╚══██╔══╝
   █████╗  ██║     ██║   ██║   ███████║██║  ███╗█████╗  ██╔██╗██║   ██║
   ██╔══╝  ██║     ██║   ██║   ██╔══██║██║   ██║██╔══╝  ██║╚████║   ██║
   ███████╗╚██████╗╚██████╔╝   ██║  ██║╚██████╔╝███████╗██║ ╚███║   ██║
   ╚══════╝ ╚═════╝ ╚═════╝    ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚══╝   ╚═╝
"""


def _build_messages(history, question, system_extra=""):
    from agent_core.prompt_engine import get_prompt_engine

    eng = get_prompt_engine()
    # system_extra 若已是 prompt_engine 产出（含安全层标记，如 workspace 注入路径），
    # 直接作为完整系统提示词，避免安全层重复拼接
    if system_extra and "【安全准则" in system_extra:
        system = system_extra
    else:
        system = eng.build_system_prompt(extra=system_extra)
    from eco.trace import get_tracer

    tracer = get_tracer()
    if getattr(tracer, "enabled", False):
        tracer.system_prompt(system, soul_loaded=getattr(eng.soul, "loaded", False))
    messages = [{"role": "system", "content": system}]
    for h in history[-10:]:
        messages.append(h)
    messages.append({"role": "user", "content": question})
    return messages


def _workspace_system_extra(query: str = "", tracer=None):
    """当前工作区内容（有 query 时按相关性混合检索片段，否则摘要）经 prompt_engine
    注入校验后进入动态层，返回拼接进 system 的文本"""
    from agent_core.workspace import get_workspace_manager

    mgr = get_workspace_manager()
    ws = mgr.current()
    if ws is None:
        return ""
    if tracer is not None and getattr(tracer, "enabled", False) and query.strip():
        try:
            hits = ws.relevant_history(query)
            tracer.retrieval(len(hits), hits[0].get("channel", "bm25") if hits else "")
        except Exception:
            pass
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


def _restore_session(args):
    """会话恢复：--resume <slug> 按名恢复；--continue 恢复最近活跃工作区。
    从 ~/.eco/workspaces/<slug>/history.jsonl 重建 history（user/assistant 事件）。"""
    slug = getattr(args, "resume", None)
    cont = getattr(args, "continue_session", False)
    if not slug and not cont:
        return []
    from agent_core.workspace import get_workspace_manager

    mgr = get_workspace_manager()
    ws = None
    if slug:
        ws = mgr.open(slug)
        if ws is None:
            print(f"[resume] 未找到工作区: {slug}（eco workspace list 查看可恢复会话）")
            return []
    else:
        cands = mgr.list()
        if not cands:
            print("[continue] 暂无历史工作区可恢复")
            return []
        cands.sort(key=lambda m: m.get("updated_at", ""), reverse=True)
        ws = mgr.open(cands[0]["slug"])
    if ws is None:
        return []
    history = []
    for rec in ws.history():
        kind, content = rec.get("kind"), rec.get("content")
        if kind == "user":
            history.append({"role": "user", "content": content})
        elif kind == "assistant":
            history.append({"role": "assistant", "content": content})
    print(f"[session] 已恢复工作区「{ws.meta.get('name', ws.path.name)}」会话历史 {len(history)} 条消息")
    return history


# 复杂任务 DAG 计划（与 RoleSwarm 执行图一致）：patrol ∥ law -> doc -> synthesis
_DAG_PLAN = [
    ("patrol", "巡查Agent 现场核查产出", []),
    ("law", "法规Agent 法条核验", []),
    ("doc", "文书Agent 起草检查记录/清单", ["patrol", "law"]),
    ("synthesis", "总管仲裁合成最终答复", ["doc"]),
]
# swarm on_stage 阶段标签 -> DAG 步骤 id（命中即勾选对应 todo）
_STAGE_DONE = {"巡查Agent 完成": "patrol", "法规Agent 完成": "law", "文书Agent 完成": "doc", "总管合成完成": "synthesis"}


def _dag_edges_text() -> list[str]:
    edges = []
    for sid, _desc, deps in _DAG_PLAN:
        edges += [f"{d} -> {sid}" for d in deps]
    return edges


def _maybe_swarm(q, context="", tracer=None):
    """复杂执法任务启用三角色协作；简单问答返回 None。
    主路径 DAG 接线：is_complex_task 判定后先生成任务分解写入工作区 todos
    （用户可见，/todo 查看），每个 DAG 步骤完成即勾选 todos.md；
    -v 模式展示 DAG 边（patrol∥law→doc→synthesis）。"""
    from agent_core.role_swarm import get_role_swarm, is_complex_task

    if not is_complex_task(q):
        return None
    swarm = get_role_swarm()
    verbose = tracer is not None and getattr(tracer, "enabled", False)
    on_stage = tracer.swarm_stage if verbose else None

    # ── 任务分解（DAG → workspace todos）──
    ws = None
    try:
        from agent_core.workspace import get_workspace_manager

        ws = get_workspace_manager().current()
        if ws is not None:
            ws.append_todo(f"[plan] 复杂任务分解：{q[:60]}")
            for sid, desc, _deps in _DAG_PLAN:
                ws.append_todo(f"[dag:{sid}] {desc}")
    except Exception:
        pass
    if verbose:
        tracer._emit("  [dag] 任务分解: " + "；".join(_dag_edges_text()), style="#7ab8a0")
        tracer._audit("[dag] " + "；".join(_dag_edges_text()), phase="dag")

    # ── 步骤完成即勾选 todos.md（逐步执行打勾可见）──
    def _on_stage(stage, detail="", elapsed=0.0):
        if on_stage is not None:
            on_stage(stage, detail, elapsed)
        sid = _STAGE_DONE.get(stage)
        if sid and ws is not None:
            try:
                ws.complete_todo(f"[dag:{sid}]")
                if verbose:
                    tracer._emit(f"  [dag] ✓ {sid} 已勾选 todos.md", style="#5ae0a0")
            except Exception:
                pass

    result = swarm.run(q, context=context, on_stage=_on_stage)
    print(swarm.format_result(result))
    # 兜底：swarm 异常时未触发的步骤不勾选；正常走完全部勾选（含 synthesis）
    if ws is not None:
        try:
            for sid in ("patrol", "law", "doc", "synthesis"):
                if result.get("contributions", {}).get(sid) or sid == "synthesis" and result.get("synthesis"):
                    ws.complete_todo(f"[dag:{sid}]")
            if result.get("synthesis"):
                ws.complete_todo("[plan]")
        except Exception:
            pass
    return result["synthesis"] or "\n".join(f"[{r}] {t}" for r, t in result["contributions"].items())


def _safe(text):
    if _IS_WINDOWS:
        try:
            text.encode(sys.stdout.encoding)
            return text
        except Exception:
            return "".join(c for c in text if ord(c) < 65536)
    return text


def _stream_answer(messages, tracer=None):
    from agent_core.llm_client import get_default_client
    from agent_core.tools_registry import attach_mcp_tools, get_tools

    c = get_default_client()
    if not c.available():
        print("[LLM not configured. Run: eco setup]")
        return ""
    attach_mcp_tools()  # ECO_MCP_SERVERS 配置的远程工具并入（幂等，未配置则跳过）
    # ── 结构化 span 树：会话根 span → llm_call → tool_call 嵌套，落 ~/.eco/traces/ ──
    from agent_core.observability import SpanTree

    tree = SpanTree(
        meta={
            "provider": getattr(c, "_provider_name", ""),
            "model": (getattr(c, "_provider", None) or {}).get("default_model", ""),
        }
    )
    root_span = tree.start("chat", "session")
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
    try:
        result = c.chat_with_tools(
            messages, tools=tools, on_chunk=on_chunk, max_tool_rounds=5, tracer=tracer, stream=True, spans=tree
        )
    except KeyboardInterrupt:
        # 生成中 Ctrl+C：取消当前生成、保留会话（不杀进程、不丢历史）
        print("\n[已取消当前生成，会话保留；可继续输入或 /exit 退出]")
        result = "[生成被用户取消]"
    tree.end(root_span)
    tree.close_all()
    try:
        path = tree.save()
        if tracer is not None and getattr(tracer, "enabled", False):
            tracer._emit(f"  [trace] span 树已落盘: {path}（eco trace --tree {tree.session_id}）", style="#8a8a8a")
    except Exception:
        pass
    return result


def _user_input_blocked(text: str):
    """用户原始输入同样过注入防线（此前只校验动态注入内容，用户输入裸奔）。
    命中返回拒绝原因字符串，未命中返回 None。"""
    from agent_core.prompt_engine import validate_injection

    ok, reason = validate_injection(text)
    return None if ok else reason


def run(args):
    from eco.trace import get_tracer, set_verbose

    set_verbose(getattr(args, "verbose", False))
    restored = _restore_session(args)
    if args.query:
        blocked = _user_input_blocked(args.query)
        if blocked:
            print(f"[安全拦截] 输入命中注入防线：{blocked}")
            return 2
        tracer = get_tracer()
        _handle_resume_intent(args.query)
        extra = _combine_extra(_workspace_system_extra(args.query, tracer=tracer))
        answer = _maybe_swarm(args.query, tracer=tracer)
        if answer is None:
            messages = _build_messages(restored, args.query, system_extra=extra)
            _stream_answer(messages, tracer=tracer)
        print()
        return 0
    return _repl(history=restored)


_HELP_TEXT = """  REPL 命令：
    /help      显示本帮助
    /exit      退出会话（/quit 同义）
    /new       清空当前会话历史，重新开始
    /ws        查看当前工作区摘要（无则提示）
    /todo      查看当前工作区待办（复杂任务 DAG 步骤在此勾选进度）
    /verbose   切换轨迹模式（思考/工具调用/耗时/DAG 边，写入 SM3 审计链）
    /model [名称]  查看当前模型与可选 provider（✅=已配 Key）；带名称则运行时切换
    /plan      规划模式：先出分步计划，确认后再执行
    /spec      规格模式：先澄清需求并产出 SPEC，对齐后再实现
    /goal      目标模式：转为带完成判据的目标，逐轮推进直到满足
    /auto      自动模式：自主拆解、连续多步推进，减少确认
    /chat      返回普通对话模式
    /checkpoints  列出会话检查点（每轮输入前自动快照）
    /rewind [n]   回滚到第 n 个检查点（默认最近一个）：截断会话历史并还原工作区文件
  生成中 Ctrl+C 只取消当前回答，会话保留。
  相关 CLI：eco trace --tree <session> 查看 span 树；eco auth grant 生成 L4 授权；eco doctor 体检。
"""


def _banner_summary() -> str:
    """启动横幅一行摘要：provider/model/workspace/权限闸门状态"""
    try:
        from agent_core.llm_client import get_default_client

        c = get_default_client()
        s = c.get_stats()
        llm = f"{s['provider']}/{s['model']}" if s.get("has_api_key") else "未配置(eco setup)"
    except Exception:
        llm = "未知"
    try:
        from agent_core.workspace import get_workspace_manager

        ws = get_workspace_manager().current_name() or "无"
    except Exception:
        ws = "无"
    import os as _os

    gate_env = _os.environ.get("ECO_PERMISSION_GATE", "").strip().lower()
    gate = "关闭(ECO_PERMISSION_GATE=0)" if gate_env == "0" else "开启"
    return f"  provider/model: {llm}  |  workspace: {ws}  |  权限闸门: {gate}"


def _self_system_extra() -> str:
    """ECO AGENT 自述信息（当前模型与切换方式），随动态层注入系统提示词：
    用户问"如何切换模型/怎么配置/有哪些命令"等关于本产品的元问题时，
    模型照此事实直接作答，而不是用"不在能力范围"套话拒绝。"""
    try:
        from agent_core.llm_client import get_default_client

        s = get_default_client().get_stats()
        llm = f"{s['provider']}/{s['model']}" if s.get("has_api_key") else "未配置(eco setup)"
    except Exception:
        llm = "未知"
    return (
        "【ECO AGENT 自述信息】\n"
        f"- 当前底层模型: {llm}\n"
        "- 切换模型: 对话内输入 /model 查看可选 provider 并切换（本次会话生效）；"
        "持久化默认模型用 `eco config model use <名称>`，清单见 `eco config model list`"
        "（支持 deepseek/moonshot/qwen/zhipu/doubao 等 15 家），"
        "连通验证用 `eco config model test <名称>`\n"
        "- 其它入口: eco setup（配置向导）、eco doctor（健康检查）、/help（对话内命令）\n"
        "用户询问 ECO AGENT 自身的使用方法、配置或模型切换属于本产品的正常使用范畴，"
        "依据以上事实简要、直接回答，不要拒绝。"
    )


def _model_cmd_text(arg: str) -> str:
    """Kimi 风格 /model：空参列出当前与可选 provider；带名称运行时切换"""
    from agent_core.llm_client import get_default_client
    from agent_core.llm_providers import PROVIDERS as _REG

    client = get_default_client()
    if not arg:
        s = client.get_stats()
        cur = f"{s['provider']}/{s['model']}" if s.get("has_api_key") else "未配置(eco setup)"
        lines = [f"[model] 当前: {cur}", "[model] 可选 provider（✅=已配置 Key，/model <名称> 切换）:"]
        for name, spec in _REG.items():
            mark = "✅" if spec.has_key() else "  "
            lines.append(f"  {mark} {name:<12} {spec.display}  默认模型: {spec.default_model}")
        lines.append("[model] 持久化默认模型: eco config model use <名称>")
        return "\n".join(lines)
    if arg not in _REG:
        return f"[model] 未知 provider: {arg}（可选: {'、'.join(_REG)}）"
    if client.switch_provider(arg):
        s = client.get_stats()
        return f"[model] 已切换到 {arg}（当前模型 {s.get('model', '?')}，本次会话生效；持久化请 eco config model use {arg}）"
    spec = _REG[arg]
    return f"[model] 切换失败：未检测到 {spec.env_key}。先在 ~/.eco/.env 配置该 Key，或用 eco config model test {arg} 排查"


def _combine_extra(extra: str, mode: str = "chat") -> str:
    """把自述信息与当前模式指令拼进动态层（workspace 片段在前，自述/模式在后）"""
    parts = [p for p in (extra, _self_system_extra()) if p]
    if mode in _MODES:
        parts.append(_MODES[mode])
    return "\n\n".join(parts)


# 对话模式预设（对标 Kimi 的 plan/spec/goal/auto 快捷命令）：
# 切换后作为模式指令注入动态层，状态栏左侧同步显示
_MODES = {
    "plan": (
        "【模式:plan】规划模式：先输出分步实施计划（步骤、涉及对象、验证方式），"
        "等用户明确确认后再展开执行；确认前不直接给最终答案或实质性改动。"
    ),
    "spec": (
        "【模式:spec】规格模式：以需求规格说明为中心，先澄清需求并产出结构化 SPEC"
        "（目标、范围、验收标准、约束），对齐后再进入实现讨论。"
    ),
    "goal": (
        "【模式:goal】目标模式：先把用户意图转成带可验证完成判据的目标陈述，每轮自检与目标的差距并给出下一步，直到判据满足。"
    ),
    "auto": (
        "【模式:auto】自动模式：在不越权（L4 操作仍需授权）、不破坏的前提下，主动拆解任务、连续多步推进，减少向用户反复确认。"
    ),
}

# 输入框长文本阈值（字符）：超过则落盘为 txt，消息体替换为文件引用（对标 Kimi 的粘贴压缩）
_PASTE_THRESHOLD = 2000


def _maybe_compress_paste(q: str) -> str:
    """输入框收到长文时自动压缩：写入 ~/.eco/paste/*.txt，返回文件引用消息；
    模型可用 analyze_document 工具按路径读取全文。短文本/斜杠命令原样返回。"""
    if len(q) <= _PASTE_THRESHOLD or q.startswith("/"):
        return q
    import time
    from pathlib import Path

    d = Path.home() / ".eco" / "paste"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"paste-{time.strftime('%Y%m%d-%H%M%S')}.txt"
    p.write_text(q, encoding="utf-8")
    print(f"[paste] 长文本 {len(q)} 字已自动保存: {p}")
    return (
        f"用户粘贴了一段长文本（共 {len(q)} 字），已保存到文件 {p}。"
        f"请先调用 analyze_document 工具（file_path={p}）读取全文，"
        f"再按文本本身的意图处理；若文本末尾带有明确问题或指令，优先响应它。"
    )


def _display_width(s: str) -> int:
    """终端显示宽度（中日韩全角字符按 2 计）"""
    import unicodedata

    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in s)


def _term_width() -> int:
    import shutil

    return shutil.get_terminal_size((80, 20)).columns


def _context_limit() -> int:
    """上下文窗口大小（token），默认 64k，可用 ECO_CONTEXT_LIMIT 覆盖"""
    import os

    try:
        return int(os.environ.get("ECO_CONTEXT_LIMIT", "64000"))
    except ValueError:
        return 64000


def _context_status(history) -> str:
    """右侧 context 用量（字符数/4 粗估 token，仅供显示）"""
    used = sum(len(m.get("content", "")) for m in history) // 4
    limit = _context_limit()
    pct = min(used * 100 // limit, 100)
    return f"context: {pct}% ({used / 1000:.1f}k/{limit // 1000}k)"


def _status_left(mode: str = "chat") -> str:
    """左侧状态：模式 + provider/model + 工作区 + 权限闸门（对标 Kimi 左栏）"""
    try:
        from agent_core.llm_client import get_default_client

        s = get_default_client().get_stats()
        llm = f"{s['provider']}/{s['model']}" if s.get("has_api_key") else "未配置(eco setup)"
    except Exception:
        llm = "未知"
    try:
        from agent_core.workspace import get_workspace_manager

        ws = get_workspace_manager().current_name() or "无"
    except Exception:
        ws = "无"
    import os as _os

    gate = "off" if _os.environ.get("ECO_PERMISSION_GATE", "").strip().lower() == "0" else "on"
    return f" {mode}  {llm}  ws:{ws}  gate:{gate}"


def _status_bar(history, mode: str = "chat") -> str:
    """Kimi 风格状态栏：左对齐模式/模型/工作区/闸门，右对齐 context 用量"""
    left = _status_left(mode)
    right = _context_status(history) + " "
    pad = max(_term_width() - _display_width(left) - _display_width(right), 1)
    return left + " " * pad + right


def _print_status_bar(history, mode: str = "chat"):
    if _HAVE_RICH:
        _console.print(_status_bar(history, mode), style="dark_green")
    else:
        print(_status_bar(history, mode))


def _boxed_input(history, mode: str = "chat") -> str:
    """Kimi 风格圆角输入框：上边框 → │ > 读入 → 下边框 → 状态栏（紧随框下）"""
    bar = "─" * (min(_term_width(), 100) - 2)
    if _HAVE_RICH:
        _console.print(f"╭{bar}╮", style="dark_green")
    else:
        print(f"╭{bar}╮")
    try:
        return input("│ > ")
    finally:
        if _HAVE_RICH:
            _console.print(f"╰{bar}╯", style="dark_green")
        else:
            print(f"╰{bar}╯")
        _print_status_bar(history, mode)


def _checkpoint_store(mgr):
    """当前会话检查点存储：会话 id 取当前工作区 slug，无工作区用 default"""
    from agent_core.checkpoint import CheckpointStore

    session = mgr.current_name() or "default"
    return CheckpointStore(session=session)


def _auto_checkpoint(mgr, history):
    """每轮用户输入前自动快照（静默失败不影响会话）"""
    try:
        store = _checkpoint_store(mgr)
        store.create(history=history, ws=mgr.current())
    except Exception as e:
        logging.getLogger("checkpoint").warning(f"[checkpoint] 快照失败: {e}")


def _repl(history=None):
    history = list(history or [])
    if history:
        print(f"[session] 继续上次会话（已载入 {len(history)} 条消息，/new 可清空重来）")
    if _HAVE_RICH:
        from rich.text import Text

        _console.print()
        _console.print(Text(LOGO, style="dark_green"))
        _console.print(Text(f"  ECO AGENT v{__version__}  --  Environmental Regulation AI", style="dark_green bold"))
        _console.print(Text(_banner_summary(), style="dark_green"))
        _console.print()
        tips = (
            "  /help      查看全部命令\n"
            "  /new       开启新会话\n"
            "  /verbose   切换轨迹模式（思考/工具调用/耗时）\n"
            "  /exit      退出（生成中 Ctrl+C 只取消当前回答）"
        )
        _console.print(
            Panel(
                tips,
                title="快速上手",
                title_align="left",
                border_style="dark_green",
                box=box.ROUNDED,
                padding=(0, 1),
            )
        )
        _console.print()
    else:
        print(LOGO)
        print(f"  ECO AGENT v{__version__}  --  Environmental Regulation AI")
        print(_banner_summary())
        print("  /help 命令帮助 | /new 新会话 | /verbose 轨迹模式 | /exit 退出")
        print()

    from agent_core.workspace import get_workspace_manager

    mgr = get_workspace_manager()
    mode = "chat"
    while True:
        try:
            q = _boxed_input(history, mode).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not q:
            continue
        if q in ("/exit", "/quit"):
            break
        if q == "/help":
            print(_HELP_TEXT)
            continue
        if q in ("/plan", "/spec", "/goal", "/auto"):
            mode = q[1:]
            print(f"[mode] 已切换到 {mode} 模式（/chat 返回普通对话）")
            continue
        if q == "/chat":
            mode = "chat"
            print("[mode] 已返回普通对话模式")
            continue
        if q == "/todo":
            cur = mgr.current()
            if cur is None:
                print("[todo] 当前无打开的工作区（用 eco workspace create/open 或先提问自动续接）")
            else:
                t = cur.todos().strip()
                print(t if t else "[todo] 当前工作区暂无待办（任务计划中产生的待办会显示在这里）")
            continue
        if q == "/verbose":
            from eco.trace import get_tracer, set_verbose

            on = set_verbose(not get_tracer().enabled)
            print(f"[trace] verbose 轨迹模式: {'开启' if on else '关闭'}")
            continue
        if q == "/new":
            history = []
            print("[reset]")
            continue
        if q == "/checkpoints":
            store = _checkpoint_store(mgr)
            cps = store.list()
            if not cps:
                print("[checkpoints] 当前会话暂无检查点（每轮输入前自动快照）")
            else:
                print(f"[checkpoints] 会话 {store.session} 共 {len(cps)} 个检查点：")
                for cp in cps:
                    nfiles = len(cp.get("workspace", {}).get("files", {}))
                    print(
                        f"  #{cp['id']}  {cp.get('ts', '')}  "
                        f"历史 {len(cp.get('history', []))} 条  "
                        f"decisions {cp.get('decisions_count', 0)}  "
                        f"工作区文件 {nfiles} 个"
                    )
            continue
        if q.startswith("/rewind"):
            parts = q.split()
            store = _checkpoint_store(mgr)
            cps = store.list()
            if not cps:
                print("[rewind] 无可回滚的检查点")
                continue
            n = cps[-1]["id"]
            if len(parts) > 1:
                try:
                    n = int(parts[1])
                except ValueError:
                    print(f"[rewind] 无效检查点编号: {parts[1]}（/checkpoints 查看可用编号）")
                    continue
            cp = store.rewind(n, ws=mgr.current())
            if cp is None:
                print(f"[rewind] 检查点 #{n} 不存在或已损坏（/checkpoints 查看可用编号）")
                continue
            history = list(cp.get("history", []))
            print(f"[rewind] 已回滚到检查点 #{n}（会话历史 {len(history)} 条，工作区文件按快照还原）")
            continue
        if q == "/model" or q.startswith("/model "):
            print(_model_cmd_text(q[len("/model") :].strip().lower()))
            _print_status_bar(history, mode)
            continue
        q = _maybe_compress_paste(q)
        blocked = _user_input_blocked(q)
        if blocked:
            print(f"[安全拦截] 输入命中注入防线：{blocked}")
            continue
        if q == "/ws":
            cur = mgr.current()
            print(mgr.current().summary() if cur else "[workspace] 当前无打开的工作区")
            continue

        _auto_checkpoint(mgr, history)
        _handle_resume_intent(q)
        ws = mgr.current()
        context = ws.summary() if ws else ""
        from eco.trace import get_tracer

        tracer = get_tracer()
        extra = _combine_extra(_workspace_system_extra(q, tracer=tracer), mode)

        answer = _maybe_swarm(q, context=context, tracer=tracer)
        if answer is None:
            messages = _build_messages(history, q, system_extra=extra)
            answer = _stream_answer(messages, tracer=tracer)
        print()

        history.append({"role": "user", "content": q})
        history.append({"role": "assistant", "content": answer})
        if len(history) > 100:
            history = history[-50:]
        if ws:
            ws.add_event("user", q)
            ws.add_event("assistant", answer[:800])
    return 0
