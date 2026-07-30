"""
eco evolution - L4 Evolution loop trigger
"""
import sys, logging
from pathlib import Path
log = logging.getLogger("eco.evolution")
logging.basicConfig(level=logging.INFO, format="%(message)s")
ROOT = Path(__file__).resolve().parent.parent.parent

def run(args):
    try:
        sys.path.insert(0, str(ROOT))
        from agent_core.meta_evolution import MetaEvolution
    except ImportError as e:
        log.error(f"Cannot load evolution engine: {e}")
        return 1
    evo = MetaEvolution()
    if args.dry_run:
        log.info("Dry run mode...")
        r = evo.analyze(dry_run=True)
        print(r)
        return 0
    if args.report:
        log.info("Generating evolution report...")
        r = evo.generate_report()
        print(r)
        # 提示词审计链状态 + 最近 EcoBench 分数（进化有效性量化证据）
        try:
            from agent_core.prompt_engine import PromptAuditChain
            v = PromptAuditChain().verify_chain()
            print(f"\n[Prompt Audit Chain] entries={v['entries']} valid={v['valid']}")
        except Exception as e:
            print(f"\n[Prompt Audit Chain] check failed: {e}")
        try:
            import json as _json
            rp = ROOT / "benchmarks" / "ecobench" / "ecobench_report.json"
            if rp.exists():
                rep = _json.loads(rp.read_text(encoding="utf-8"))
                sm = rep.get("summary", {})
                print(f"[EcoBench-mini] last run: citation_acc={sm.get('citation_accuracy')} "
                      f"keypoint_f1={sm.get('keypoint_f1')} n={sm.get('n_questions')}")
        except Exception:
            pass
        return 0
    log.info("Running full evolution cycle...")
    r = evo.run_full_cycle()
    print(r or "Evolution complete")
    return 0
