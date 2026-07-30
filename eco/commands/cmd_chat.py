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
    except ImportError as e:
        log.error(f"Cannot load engine: {e}")
        return 1
    if query:
        return _oneshot(query)
    return _interactive()

def _get_answer(query):
    """Get real answer via ReAct++ with LLM fallback"""
    try:
        from agent_core.react_loop import ReActPlusPlus
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

def _oneshot(query):
    print()
    answer = _get_answer(query)
    print(answer)
    print()
    return 0

def _interactive():
    print()
    print("  ECO AGENT - Ask me anything")
    print()
    while True:
        try:
            q = input("eco> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            print("Bye!")
            break
        if not q: continue
        if q in ("/exit", "/quit"): break
        if q == "/help":
            print("  /help  /exit")
            continue
        print()
        answer = _get_answer(q)
        print(answer)
        print()
    return 0
