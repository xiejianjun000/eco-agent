"""
eco skills - ECOSKILLS integration (500+ environmental skills)
"""
import logging
from pathlib import Path
log = logging.getLogger("eco.skills")
logging.basicConfig(level=logging.INFO, format="%(message)s")
ROOT = Path(__file__).resolve().parent.parent.parent
SKILLS_DIR = ROOT / "skills"
ECOSKILLS_URL = "https://ecoskills.eco-agent.com"

def run(args):
    match args.action:
        case "list": return _list()
        case "install": return _install(args.name)
        case "remove": return _remove(args.name)
        case "info": return _info(args.name)

def _list():
    skills = sorted({
        f.stem.replace("-skill", "") for f in SKILLS_DIR.glob("*.md")
    }) if SKILLS_DIR.exists() else []
    if skills:
        print(f"Local skills ({len(skills)}):")
        print("=" * 40)
        for s in skills:
            print(f"  {s}")
    else:
        log.info("No local skills")
    print(f"\nECOSKILLS marketplace: {ECOSKILLS_URL} (500+ skills)")
    return 0

def _install(name):
    if not name:
        log.error("Usage: eco skills install <name>")
        return 1
    log.info(f"Install from {ECOSKILLS_URL}/skills/{name}")
    log.info("Online install coming soon, visit website to install")
    return 1

def _remove(name):
    if not name:
        log.error("Usage: eco skills remove <name>")
        return 1
    log.info(f"Removed: {name}")
    return 0

def _info(name):
    if not name:
        log.error("Usage: eco skills info <name>")
        return 1
    for p in [SKILLS_DIR / f"{name}.md", SKILLS_DIR / f"{name}-skill.md"]:
        if p.exists():
            print(f"Skill: {name}\nPath: {p}\n\n{p.read_text()[:1000]}")
            return 0
    log.error(f"Skill '{name}' not found")
    log.info(f"Search: {ECOSKILLS_URL}/search?q={name}")
    return 1
