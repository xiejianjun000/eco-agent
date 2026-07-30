"""
eco chat - Talk to ECO AGENT (5-layer loop engine)
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
        from agent_core.eco_loops_integration import EcoLoops
    except ImportError as e:
        log.error(f"Cannot load engine: {e}")
        return 1
    loops = EcoLoops()
    loops.start()
    if query:
        return _oneshot(loops, query)
    return _interactive(loops)

def _oneshot(loops, q):
    log.info(f"\n  Q: {q}\n")
    try:
        r = loops.execute_task(q)
        out = r.get("output", r.get("result", str(r))) if isinstance(r, dict) else r
        print(out)
        return 0
    except Exception as e:
        log.error(f"Error: {e}")
        return 1
    finally:
        loops.stop()

def _interactive(loops):
    print("\n  ECO AGENT interactive mode (/help /exit /evo /stats)\n")
    while True:
        try:
            q = input("eco> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break
        if not q:
            continue
        if q in ("/exit", "/quit"):
            break
        if q == "/help":
            print("  /help /exit /evo /stats")
            continue
        if q == "/evo":
            try:
                r = loops.run_evolution()
                print(r or "Evolution done")
            except Exception as e:
                log.error(f"Evolution failed: {e}")
            continue
        if q == "/stats":
            for k, v in loops.get_stats().items():
                print(f"  {k}: {v}")
            continue
        try:
            r = loops.execute_task(q)
            out = r.get("output", r.get("result", str(r))) if isinstance(r, dict) else r
            print(f"\n{out}\n")
        except Exception as e:
            log.error(f"Error: {e}")
    loops.stop()
    return 0
