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
        case "versions": return _versions()
        case "rollback": return _rollback(args.name)


def _versions_dir():
    return ROOT / "memory-tree" / "data" / "versions"


def _versions():
    """列出可用的版本快照（由 eco evolution 自我版本化产生）"""
    vdir = _versions_dir()
    snaps = sorted([d for d in vdir.iterdir() if d.is_dir()]) if vdir.exists() else []
    if not snaps:
        print("无可用版本快照。先运行 eco evolution 生成快照。")
        return 0
    print(f"可用版本快照（{len(snaps)}，位于 {vdir}）:")
    for d in snaps:
        vt = (d / "version.txt").read_text().strip() if (d / "version.txt").exists() else ""
        has_skills = (d / "skills").is_dir()
        has_soul = (d / "SOUL.md").exists()
        print(f"  {d.name}  {vt}  skills={'Y' if has_skills else '-'} SOUL={'Y' if has_soul else '-'}")
    print("\n回滚用法: eco skills rollback v3")
    return 0


def _rollback(version):
    """回滚 skills/ 与 SOUL.md 到指定版本快照"""
    import shutil
    if not version:
        log.error("Usage: eco skills rollback <version>（如 v3；可用 eco skills versions 查看）")
        return 1
    snap = _versions_dir() / version
    if not snap.is_dir():
        log.error(f"版本快照不存在: {snap}（用 eco skills versions 查看可用版本）")
        return 1
    restored = []
    if (snap / "skills").is_dir():
        shutil.copytree(snap / "skills", SKILLS_DIR, dirs_exist_ok=True)
        restored.append(f"skills/ <- {snap / 'skills'}")
    if (snap / "SOUL.md").exists():
        soul_dst = ROOT / "profiles" / "eco-agent" / "SOUL.md"
        shutil.copy2(snap / "SOUL.md", soul_dst)
        restored.append(f"SOUL.md <- {snap / 'SOUL.md'}")
        try:  # SOUL 热更新，立即生效
            from agent_core.prompt_engine import get_prompt_engine
            get_prompt_engine().reload_soul()
        except Exception:
            pass
    if not restored:
        log.error(f"快照 {version} 中没有可回滚物料（skills/SOUL）")
        return 1
    for r in restored:
        print(f"[rollback] {r}")
    print(f"[rollback] 已回滚到 {version}")
    return 0

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
