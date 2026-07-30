"""
eco chat — Talk to ECO AGENT (via ReAct++ for real LLM responses)
"""
import sys, logging
from pathlib import Path
log = logging.getLogger("eco.chat")
logging.basicConfig(level=logging.INFO, format="%(message)s")
ROOT = Path(__file__).resolve().parent.parent.parent

def run(args):
    query = args.query
    try:
        sys.path.insert(0, str(ROOT))
        from agent_core.react_loop import ReActPlusPlus
        from agent_core.llm_client import get_default_client
    except ImportError as e:
        log.error(f"Cannot load engine: {e}")
        return 1

    if query:
        return _oneshot(query, ReActPlusPlus)
    return _interactive(ReActPlusPlus)

def _get_answer(query, ReActPlusPlus):
    """通过 ReAct++ + LLM fallback 获取真实回答"""
    try:
        loop = ReActPlusPlus()
        result = loop.execute(query)
        if isinstance(result, dict):
            obs = result.get("final_observation", "")
            if obs and obs != "任务完成":
                return obs
        # Fallback: direct LLM
        from agent_core.llm_client import get_default_client
        c = get_default_client()
        if c.available():
            r = c.chat([{"role": "user", "content": query}])
            return r.get("choices", [{}])[0].get("message", {}).get("content", str(result))
        return str(result)
    except Exception as e:
        return f"[Error: {e}]"

def _oneshot(query, ReActPlusPlus):
    print()
    answer = _get_answer(query, ReActPlusPlus)
    print(answer)
    print()
    return 0

def _interactive(ReActPlusPlus):
    print("
  ECO AGENT - Ask me anything about environmental regulations
")
    while True:
        try:
            q = input("eco> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("
Bye!"); break
        if not q: continue
        if q in ("/exit", "/quit"): break
        if q == "/help":
            print("  /help  /exit
")
            continue
        print()
        answer = _get_answer(q, ReActPlusPlus)
        print(answer)
        print()
    return 0
