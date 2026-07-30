"""
eco chat - Talk to ECO AGENT (direct LLM, clean output)
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
    """Get answer directly from LLM"""
    try:
        from agent_core.llm_client import get_default_client
        c = get_default_client()
        if c.available():
            r = c.chat([{"role": "user", "content": query}])
            return r.get("choices", [{}])[0].get("message", {}).get("content", "")
        return "[LLM not configured. Run: eco setup]"
    except Exception as e:
        return f"[Error: {e}]"

def _oneshot(query):
    answer = _get_answer(query)
    print(answer)
    return 0

def _interactive():
    print("  ECO AGENT - ask me anything")
    print()
    while True:
        try:
            q = input("eco> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not q: continue
        if q in ("/exit", "/quit"): break
        if q == "/help":
            print("  /exit")
            continue
        answer = _get_answer(q)
        print()
        print(answer)
        print()
    return 0
