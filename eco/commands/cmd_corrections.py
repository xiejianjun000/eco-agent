"""
eco corrections - 用户纠错管理（采集自 eco chat 的 /correct 与自然语言纠错）
"""
import logging
log = logging.getLogger("eco.corrections")
logging.basicConfig(level=logging.INFO, format="%(message)s")


def run(args):
    from agent_core.corrections import CorrectionStore
    store = CorrectionStore()
    match args.action:
        case "list":
            items = store.list_all()
            if not items:
                print("(no corrections yet)")
                return 0
            for it in items:
                print(f"  #{it['id']} [hits={it.get('hits', 1)}] {it['content']}")
                if it.get("context_summary"):
                    print(f"      上下文: {it['context_summary'][:80]}")
                print(f"      记录于: {it.get('created_at', '?')}")
            print(f"\n  total: {len(items)}")
            return 0
        case "remove":
            if args.value is None:
                log.error("Usage: eco corrections remove <id>")
                return 1
            try:
                idx = int(args.value)
            except ValueError:
                log.error("id must be an integer")
                return 1
            if store.remove(idx):
                log.info(f"Removed correction #{idx}")
                return 0
            log.error(f"Correction #{idx} not found")
            return 1
        case "clear":
            n = store.clear()
            log.info(f"Cleared {n} corrections")
            return 0
        case _:
            log.error("Usage: eco corrections list|remove <id>|clear")
            return 1
