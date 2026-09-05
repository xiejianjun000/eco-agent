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
        case "list":
            return _list()
        case "install":
            return _install(args.name, force=getattr(args, "force", False))
        case "remove":
            return _remove(args.name)
        case "info":
            return _info(args.name)
        case "versions":
            return _versions()
        case "rollback":
            return _rollback(args.name)
        case "search":
            return _search(args.name)
        case "scan":
            return _scan(args.name)
        case "sign":
            return _sign(args.name)


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
    # 1) EcoSkills 注册表（带信任徽章列）
    from agent_core.ecoskills import TIER_BADGE

    installed = _registry().list()
    if installed:
        print(f"EcoSkills registry ({len(installed)}):")
        print("=" * 60)
        for r in installed:
            m = r.get("manifest", {})
            badge = TIER_BADGE.get(m.get("trust_tier", "community"), "[社区]")
            print(f"  {badge} {r['name']:<24} v{m.get('version', '?'):<8} {m.get('description', '')[:40]}")
    skills = sorted({f.stem.replace("-skill", "") for f in SKILLS_DIR.glob("*.md")}) if SKILLS_DIR.exists() else []
    if skills:
        print(f"\nLocal skills ({len(skills)}):")
        print("=" * 40)
        for s in skills:
            print(f"  {s}")
    if not installed and not skills:
        log.info("No local skills")
    print(f"\nECOSKILLS marketplace: {ECOSKILLS_URL} (500+ skills)")
    return 0


def _install(path, force=False):
    if not path:
        log.error("Usage: eco skills install <path> [--force]")
        return 1
    if not Path(path).exists():
        # 兼容旧语义：非本地路径视为市场技能名
        log.info(f"Install from {ECOSKILLS_URL}/skills/{path}")
        log.info("Online install coming soon, visit website to install")
        return 1
    result = _registry().install(path, force=force)
    if not result.get("success"):
        log.error(f"安装失败: {result.get('error')}")
        if result.get("requires_force"):
            log.info("提示: 追加 --force 强制安装（将强制安全扫描告警）")
        return 1
    scan = result.get("scan", {})
    print(
        f"[install] {result['name']} tier={result['trust_tier']} 验签={'通过' if result.get('verified') else '跳过'} 风险={scan.get('risk_level')}"  # noqa: E501
    )
    for f in scan.get("findings", []):
        print(f"  [{f['level']}] {f['type']}: {f['detail']}")
    return 0


def _remove(name):
    if not name:
        log.error("Usage: eco skills remove <name>")
        return 1
    result = _registry().remove(name)
    if not result.get("success"):
        log.error(result["error"])
        return 1
    print(f"Removed: {name}")
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


# ═══════════════════════════════════
# EcoSkills 信任链子命令（agent_core/ecoskills.py）
# ═══════════════════════════════════


def _registry():
    from agent_core.ecoskills import SkillRegistry

    return SkillRegistry()


def _search(keyword):
    if not keyword:
        log.error("Usage: eco skills search <keyword>")
        return 1
    results = _registry().search(keyword)
    if not results:
        print(f"无匹配技能: {keyword}")
        return 0
    from agent_core.ecoskills import TIER_BADGE

    print(f"匹配技能 ({len(results)}):")
    for r in results:
        m = r.get("manifest", {})
        badge = TIER_BADGE.get(m.get("trust_tier", "community"), "[社区]")
        print(f"  {badge} {r['name']} v{m.get('version', '?')} - {m.get('description', '')}")
    return 0


def _scan(path):
    if not path:
        log.error("Usage: eco skills scan <path>")
        return 1
    from agent_core.ecoskills import scan_skill

    report = scan_skill(path)
    print(f"安全扫描报告: {path}")
    print(f"  入口: {report['entry']}")
    print(f"  风险等级: {report['risk_level']}  安全: {report['safe']}")
    if report["findings"]:
        for f in report["findings"]:
            loc = f":{f['line']}" if f.get("line") else ""
            print(f"  [{f['level']}] {f['type']}{loc} {f['detail']}")
    else:
        print("  未发现风险项")
    return 0 if report["safe"] else 1


def _sign(path):
    """官方签发：对 manifest.json 做 SM3-HMAC 签名并回写"""
    if not path:
        log.error("Usage: eco skills sign <path>")
        return 1
    import json

    from agent_core.ecoskills import SkillManifest, sign_manifest

    mp = Path(path) / "manifest.json"
    if not mp.exists():
        log.error(f"manifest.json 不存在: {mp}")
        return 1
    manifest = SkillManifest.load(path)
    sign_manifest(manifest)  # 本机签发密钥
    mp.write_text(json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[sign] 已签发: {manifest.name} v{manifest.version} tier={manifest.trust_tier}")
    return 0
