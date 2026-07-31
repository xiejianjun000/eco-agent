"""
eco trace - 结构化 span 树查看与 OTLP 导出

  eco trace                        列出 ~/.eco/traces 下的会话
  eco trace --tree <session>       树形展示某次会话的 span 树（llm_call→tool_call 嵌套）
  eco trace --tree <session> --otel [out.json]   额外导出 OTLP JSON（trace v1）
"""
from pathlib import Path

from agent_core.observability import SpanTree, TRACES_DIR


def run(args):
    session = getattr(args, "session", None)
    if not session:
        sessions = SpanTree.list_sessions()
        if not sessions:
            print(f"[trace] 暂无追踪记录（{TRACES_DIR}）；运行 eco chat 后自动生成")
            return 0
        print(f"[trace] {len(sessions)} 个会话追踪（{TRACES_DIR}）：")
        for s in sessions[-20:]:
            print(f"  {s}")
        print("用法: eco trace --tree <session> [--otel out.json]")
        return 0

    if not getattr(args, "tree", False):
        # 给了 session 但未指定 --tree，默认树形展示
        args.tree = True

    try:
        tree = SpanTree.load(session)
    except FileNotFoundError:
        print(f"[trace] 未找到会话: {session}（eco trace 查看可用列表）")
        return 1
    except Exception as e:
        print(f"[trace] 加载失败: {e}")
        return 1

    print(tree.render_tree())

    otel = getattr(args, "otel", None)
    if otel is not None:
        out = Path(otel) if otel else Path(f"{tree.session_id}.otlp.json")
        tree.export_otlp(out)
        print(f"\n[trace] OTLP JSON 已导出: {out}")
    return 0
