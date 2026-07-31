"""
eco chat - CLAUDE/CODEX/HERMES pattern
  LLM <-> Tools -> Final answer
"""
import sys

_IS_WINDOWS = sys.platform.startswith("win")
import logging
logging.basicConfig(level=logging.WARNING)

try:
    from rich.console import Console
    from rich.panel import Panel  # noqa: F401
    from rich import box  # noqa: F401
    _console = Console()
    _HAVE_RICH = True
except ImportError:
    _console = None
    _HAVE_RICH = False

# DEPRECATED: 单行硬编码提示词已废弃，系统提示词统一由 prompt_engine（SOUL 驱动）产出。
# 保留该常量仅为向后兼容外部引用。

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
    print(f"[session] 已恢复工作区「{ws.meta.get('name', ws.path.name)}」"
          f"会话历史 {len(history)} 条消息")
    return history

# 复杂任务 DAG 计划（与 RoleSwarm 执行图一致）：patrol ∥ law -> doc -> synthesis
_DAG_PLAN = [
    ("patrol", "巡查Agent 现场核查产出", []),
    ("law", "法规Agent 法条核验", []),
    ("doc", "文书Agent 起草检查记录/清单", ["patrol", "law"]),
    ("synthesis", "总管仲裁合成最终答复", ["doc"]),
]
# swarm on_stage 阶段标签 -> DAG 步骤 id（命中即勾选对应 todo）
_STAGE_DONE = {"巡查Agent 完成": "patrol", "法规Agent 完成": "law",
               "文书Agent 完成": "doc", "总管合成完成": "synthesis"}


def _dag_edges_text() -> list[str]:
    edges = []
    for sid, desc, deps in _DAG_PLAN:
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
    return result["synthesis"] or "\n".join(
        f"[{r}] {t}" for r, t in result["contributions"].items())

def _safe(text):
    if _IS_WINDOWS:
        try:
            text.encode(sys.stdout.encoding)
            return text
        except Exception:
            return ''.join(c for c in text if ord(c) < 65536)
    return text

def _stream_answer(messages, tracer=None):
    from agent_core.llm_client import get_default_client
    from agent_core.tools_registry import get_tools
    c = get_default_client()
    if not c.available():
        print("[LLM not configured. Run: eco setup]")
        return ""
    # ── 结构化 span 树：会话根 span → llm_call → tool_call 嵌套，落 ~/.eco/traces/ ──
    from agent_core.observability import SpanTree
    tree = SpanTree(meta={"provider": getattr(c, "_provider_name", ""),
                          "model": (getattr(c, "_provider", None) or {}).get("default_model", "")})
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
        result = c.chat_with_tools(messages, tools=tools, on_chunk=on_chunk, max_tool_rounds=5,
                                   tracer=tracer, stream=True, spans=tree)
    except KeyboardInterrupt:
        # 生成中 Ctrl+C：取消当前生成、保留会话（不杀进程、不丢历史）
        print("\n[已取消当前生成，会话保留；可继续输入或 /exit 退出]")
        result = "[生成被用户取消]"
    tree.end(root_span)
    tree.close_all()
    try:
        path = tree.save()
        if tracer is not None and getattr(tracer, "enabled", False):
            tracer._emit(f"  [trace] span 树已落盘: {path}（eco trace --tree {tree.session_id}）",
                         style="#8a8a8a")
    except Exception:
        pass
    return result

def run(args):
    from eco.trace import set_verbose, get_tracer
    set_verbose(getattr(args, "verbose", False))
    restored = _restore_session(args)
    if args.query:
        tracer = get_tracer()
        _handle_resume_intent(args.query)
        extra = _workspace_system_extra(args.query, tracer=tracer)
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


def _repl(history=None):
    history = list(history or [])
    if history:
        print(f"[session] 继续上次会话（已载入 {len(history)} 条消息，/new 可清空重来）")
    if _HAVE_RICH:
        from rich.text import Text
        _console.print()
        _console.print(Text(LOGO, style="#3a8a6f"))
        _console.print(Text(LOGO_LINE, style="#5ae0a0 bold"))
        _console.print(Text(_banner_summary(), style="#4a7a5a"))
        _console.print(Text("  /exit  /new  /help  /verbose  |  ECO AGENT v5.0.0a2", style="#2a5a3a"))
        _console.print()
    else:
        print(LOGO)
        print(LOGO_LINE)
        print(_banner_summary())
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
            print(_HELP_TEXT); continue
        if q == "/todo":
            cur = mgr.current()
            if cur is None:
                print("[todo] 当前无打开的工作区（用 eco workspace create/open 或先提问自动续接）")
            else:
                t = cur.todos().strip()
                print(t if t else "[todo] 当前工作区暂无待办（任务计划中产生的待办会显示在这里）")
            continue
        if q == "/verbose":
            from eco.trace import set_verbose, get_tracer
            on = set_verbose(not get_tracer().enabled)
            print(f"[trace] verbose 轨迹模式: {'开启' if on else '关闭'}")
            continue
        if q == "/new":
            history = []; print("[reset]"); continue
        if q == "/ws":
            cur = mgr.current()
            print(mgr.current().summary() if cur else "[workspace] 当前无打开的工作区")
            continue

        _handle_resume_intent(q)
        ws = mgr.current()
        context = ws.summary() if ws else ""
        from eco.trace import get_tracer
        tracer = get_tracer()
        extra = _workspace_system_extra(q, tracer=tracer)

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
