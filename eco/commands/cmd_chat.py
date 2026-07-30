"""
eco chat — Conversational AI interface
Design: CLAUDE/CODEX/HERMES pattern — direct LLM, identity-driven, clean output
"""
import sys, logging, json, time
from pathlib import Path

log = logging.getLogger("eco.chat")
logging.basicConfig(level=logging.WARNING)

ROOT = Path(__file__).resolve().parent.parent.parent

# ─── ECO Identity — loaded from SOUL.md like CLAUDE loads AGENTS.md ───
_ECO_IDENTITY = """# ECO AGENT

## 身份
我是 ECO AGENT，生态环境法规领域的 AI 助手。

## 核心原则
1. 专业 — 引用法规时标注具体条款，不确定时说明
2. 严谨 — 每个结论都要有依据，不编造信息
3. 务实 — 给出的建议可操作、可执行
4. 审慎 — 涉及执法、处罚等敏感内容，标注仅供参考

## 回答格式
- 结构化输出：使用列表、要点、分层
- 法规引用标准名称和条款号
- 涉及处罚时注明法律依据和处罚幅度
- 末尾标注「本回答仅供参考，不构成法律意见」
"""

def _build_system_prompt() -> list:
    """Build message list with ECO's identity injected as system prompt"""
    return [{"role": "system", "content": _ECO_IDENTITY}]

def _call_llm(messages: list) -> str:
    """Single LLM call — returns text response"""
    from agent_core.llm_client import get_default_client
    c = get_default_client()
    if not c.available():
        return "[LLM not configured. Run: eco setup]"
    try:
        r = c.chat(messages)
        return r.get("choices", [{}])[0].get("message", {}).get("content", "")
    except Exception as e:
        return f"[Error: {e}]"

def run(args):
    query = args.query
    if query:
        messages = _build_system_prompt()
        messages.append({"role": "user", "content": query})
        answer = _call_llm(messages)
        print(answer)
        return 0
    return _repl()

def _repl():
    """Interactive REPL — like CLAUDE/CODEX/HERMES"""
    messages = _build_system_prompt()
    print("  ECO AGENT — 生态环境法规 AI 助手")
    print("  (/exit 退出)")
    print()
    while True:
        try:
            q = input("eco> ").strip()
        except (EOFError, KeyboardInterrupt):
            print(); break
        if not q: continue
        if q in ("/exit", "/quit"): break
        if q == "/help":
            print("  /exit  退出"); continue
        if q == "/new":
            messages = _build_system_prompt()
            print("  [对话已重置]"); continue
        if q == "/system":
            print(_ECO_IDENTITY); continue
        messages.append({"role": "user", "content": q})
        answer = _call_llm(messages)
        print()
        print(answer)
        print()
        messages.append({"role": "assistant", "content": answer})
    return 0
