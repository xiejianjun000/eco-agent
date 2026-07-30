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
        return 0
    log.info("Running full evolution cycle...")
    r = evo.run_full_cycle()
    print(r or "Evolution complete")
    return 0
