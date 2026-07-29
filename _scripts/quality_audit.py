#!/usr/bin/env python3
"""
quality_audit.py — ECO AGENT 质量审计工具

审计 ECO AGENT 项目自身的文件完整性、宪法合规性、质量标准达标情况。

ECO AGENT 14 维质量评分卡ECO SCHEMA 2

  结构维度
    D1  法规溯源准确率  — 每条结论可追溯到原始法规
    D2  执法程序合规率  — 严格遵循法定程序状态机验证
    D3  置信度标注率    — 结论标注 confidence 字段
    D4  执法分析完整性  — 涵盖违法要件/依据/裁量因素

  连接维度
    D5  法规交叉引用率  — 引用相关法规的完整度
    D6  案例双向关联率  — 案例与法规双向可追溯
    D7  执法图谱连通度  — 图谱连通性
    D8  知识孤岛率      — 孤立节点占比5%

  内容维度
    D9  索引覆盖率      — 知识节点在索引中的覆盖率
    D10 法规新鲜度      — 最近确认过时效的法规占比
    D11 rawwiki覆盖率  — 原始法规对应知识条目的比例

  质量维度
    D12 反幻觉率        — 可追溯到原始法规的结论占比
    D13 断链率          — 悬空链接占比3%
    D14 系统容错度      — 删除节点后连通性保持能力

当前审计范围P0 MVP
  检测项目自身的宪法文件和目录完整性

用法
  python _scripts/quality_audit.py                # 完整审计
  python _scripts/quality_audit.py --json         # JSON 输出
  python _scripts/quality_audit.py --summary      # 仅摘要
"""

import re
import json
import argparse
from pathlib import Path
from datetime import datetime


#  项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent


#  红线阈值ECO SCHEMA 2
REDLINES = {k.split("_", 1)[1] if "_" in k else k: v for k, v in {
    # 所有 D  85%关键项  90%
    # 孤岛率  5%断链率  3%
    "D1_traceability": {"min": 0.95, "label": "法规溯源准确率"},
    "D2_procedure": {"min": 1.00, "label": "执法程序合规率"},
    "D3_confidence": {"min": 0.90, "label": "置信度标注率"},
    "D4_completeness": {"min": 0.90, "label": "执法分析完整性"},
    "D5_cross_ref": {"min": 0.95, "label": "法规交叉引用率"},
    "D6_bidirectional": {"min": 0.90, "label": "案例双向关联率"},
    "D7_connectivity": {"min": 0.90, "label": "执法图谱连通度"},
    "D8_island": {"min": 0.00, "label": "知识孤岛率", "max": 0.05},
    "D9_index": {"min": 0.95, "label": "索引覆盖率"},
    "D10_freshness": {"min": 0.80, "label": "法规新鲜度"},
    "D11_coverage": {"min": 0.90, "label": "rawwiki覆盖率"},
    "D12_anti_hallucination": {"min": 0.95, "label": "反幻觉率"},
    "D13_broken_links": {"min": 0.00, "label": "断链率", "max": 0.03},
    "D14_fault_tolerance": {"min": 0.95, "label": "系统容错度"},
}.items()}


#  必备文件清单
REQUIRED_FILES = [
    "CLAUDE.md",
    "SCHEMA.md",
    "CHANGELOG.md",
    "README.md",
    ".gitignore",
    "开发实施方案.md",
    "项目说明书.md",
]

REQUIRED_DIRS = [
    "_scripts",
    "skills",
    "profiles",
    "memory-tree",
    "tests",
    "docs",
]

PROFILE_FILES = [
    "profiles/eco-agent/config.yaml",
    "profiles/eco-agent/SOUL.md",
    "profiles/eco-agent/MEMORY.md",
    "profiles/eco-agent/PERMISSION.md",
    "profiles/eco-agent/USER.md",
    "profiles/eco-agent/install.sh",
]

SKILL_FILES = [
    "skills/query-skill.md",
    "skills/enforcement-qa-skill.md",
]

SCRIPT_FILES = [
    "_scripts/eco-knowledge-mcp.py",
]

REQUIRED_SECTIONS = {
    "CLAUDE.md": [
        ("身份", "#"),
        ("核心职责", "#"),
        ("启动协议", "#"),
        ("系统架构", "#"),
        ("Agent 团队编排", "#"),
        ("质量标准", "#"),
        ("ACE 三阶段审查循环", "#"),
        ("操作纪律", "#"),
        ("G 方法论", "#"),
    ],
    "SCHEMA.md": [
        ("知识库架构", "#"),
        ("质量标准", "#"),
        ("ACE 三阶段审查循环", "#"),
        ("操作纪律", "#"),
        ("文件格式标准", "#"),
        ("三验标准", "#"),
        ("技能孵化流程", "#"),
    ],
}


def check_project_root():
    """检测项目根目录是否存在必备目录和文件"""
    issues = []
    for d in REQUIRED_DIRS:
        if not (PROJECT_ROOT / d).is_dir():
            issues.append(f"缺少必备目录: {d}/")
    for f in REQUIRED_FILES:
        if not (PROJECT_ROOT / f).is_file():
            issues.append(f"缺少必备文件: {f}")
    return issues


def check_constitution_sections():
    """检查宪法文件的关键段落是否存在"""
    results = {}
    for fname, sections in REQUIRED_SECTIONS.items():
        fpath = PROJECT_ROOT / fname
        if not fpath.exists():
            results[fname] = {"status": "missing", "missing_sections": [s[0] for s in sections]}
            continue
        content = fpath.read_text(encoding="utf-8", errors="ignore")
        missing = []
        for section_name, heading_level in sections:
            # 支持 ## 和 ### 级标题
            pattern = rf"^#{heading_level}\s+.*{re.escape(section_name)}"
            if not re.search(pattern, content, re.MULTILINE):
                missing.append(section_name)
        results[fname] = {
            "status": "ok" if not missing else "incomplete",
            "missing_sections": missing,
        }
    return results


def count_file_lines():
    """统计各文件行数"""
    stats = {}
    for pattern in ["*.md", "*.py", "*.yaml", "*.sh"]:
        for f in PROJECT_ROOT.rglob(pattern):
            if ".git" in str(f):
                continue
            try:
                lines = len(f.read_text(encoding="utf-8", errors="ignore").splitlines())
                rel = f.relative_to(PROJECT_ROOT)
                stats[str(rel.as_posix())] = lines
            except Exception:
                pass
    return stats


def check_file_frontmatter():
    """检查 .md 文件的 YAML frontmatter"""
    results = {"total": 0, "with_frontmatter": 0, "files": []}
    for f in sorted(PROJECT_ROOT.rglob("*.md")):
        if ".git" in str(f):
            continue
        rel = f.relative_to(PROJECT_ROOT)
        results["total"] += 1
        content = f.read_text(encoding="utf-8", errors="ignore")
        if content.startswith("---"):
            end = content.find("---", 3)
            if end != -1:
                results["with_frontmatter"] += 1
                continue
        results["files"].append(str(rel.as_posix()))
    results["ratio"] = results["with_frontmatter"] / max(results["total"], 1)
    return results


def find_broken_wikilinks():
    """检测 .md 文件中的悬空 [[wikilink]]"""
    broken = []
    all_stems = set()
    all_files = list(PROJECT_ROOT.rglob("*.md"))
    for f in all_files:
        all_stems.add(f.stem)

    for f in all_files:
        if ".git" in str(f):
            continue
        content = f.read_text(encoding="utf-8", errors="ignore")
        links = re.findall(r'\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]', content)
        for link in links:
            link_name = link.strip()
            if link_name not in all_stems:
                rel = f.relative_to(PROJECT_ROOT)
                broken.append({"file": str(rel.as_posix()), "link": link_name})
    return broken


def audit_project_quality():
    """执行完整的项目质量审计"""
    start_time = datetime.now()

    print("=" * 60)
    print("  ECO AGENT 质量审计报告")
    print(f"  审计时间: {start_time.strftime('%Y-%m-%d %H:%M')}")
    print(f"  项目根目录: {PROJECT_ROOT}")
    print("=" * 60)

    # --- D1: 文件结构完整性 ---
    dir_issues = check_project_root()
    d1_score = 1.0 - (len(dir_issues) / (len(REQUIRED_DIRS) + len(REQUIRED_FILES)))
    d1_score = max(0, d1_score)
    print(f"\n[DIR] D1 文件结构完整性: {d1_score:.0%}")
    if dir_issues:
        for issue in dir_issues:
            print(f"   [FAIL] {issue}")
    else:
        print("   [OK] 全部必备文件和目录存在")

    # --- D2: 宪法段落完整性 ---
    section_results = check_constitution_sections()
    total_sections = sum(len(v["missing_sections"]) for v in section_results.values())
    all_missing = [(fname, s) for fname, v in section_results.items() for s in v["missing_sections"]]
    total_required = sum(len(v) for v in REQUIRED_SECTIONS.values())
    d2_score = 1.0 - (len(all_missing) / max(total_required, 1))
    print(f"\n[SEC] D2 宪法段落完整性: {d2_score:.0%}")
    for fname, v in section_results.items():
        if v["status"] == "missing":
            print(f"   [FAIL] {fname} 文件缺失")
        elif v["missing_sections"]:
            for s in v["missing_sections"]:
                print(f"   [WARN]  {fname} 缺少段落: {s}")

    # --- D3: Frontmatter 覆盖率 ---
    fm = check_file_frontmatter()
    d3_score = fm["ratio"]
    print(f"\n[FM]  D3 Frontmatter 覆盖率: {d3_score:.0%}")
    if fm["files"]:
        print(f"   [WARN]  缺少 frontmatter 的文件 ({len(fm['files'])} 个):")
        for f in fm["files"][:5]:
            print(f"     - {f}")

    # --- D4: Profile 文件完整性 ---
    missing_profile = [f for f in PROFILE_FILES if not (PROJECT_ROOT / f).is_file()]
    present_profile = len(PROFILE_FILES) - len(missing_profile)
    d4_score = present_profile / max(len(PROFILE_FILES), 1)
    print(f"\n[CFG]  D4 Profile 配置完整性: {d4_score:.0%}")
    for f in missing_profile:
        print(f"   [FAIL] 缺少: {f}")

    # --- D5: 技能文件完整性 ---
    missing_skills = [f for f in SKILL_FILES if not (PROJECT_ROOT / f).is_file()]
    present_skills = len(SKILL_FILES) - len(missing_skills)
    d5_score = present_skills / max(len(SKILL_FILES), 1)
    print(f"\n[SKILL] D5 技能文件完整性: {d5_score:.0%}")
    for f in missing_skills:
        print(f"   [FAIL] 缺少: {f}")

    # --- D6: 脚本文件完整性 ---
    missing_scripts = [f for f in SCRIPT_FILES if not (PROJECT_ROOT / f).is_file()]
    present_scripts = len(SCRIPT_FILES) - len(missing_scripts)
    d6_score = present_scripts / max(len(SCRIPT_FILES), 1)
    print(f"\n[SCRIPT]  D6 脚本文件完整性: {d6_score:.0%}")
    for f in missing_scripts:
        print(f"   [FAIL] 缺少: {f}")

    # --- D7: Git 提交健康度 ---
    import subprocess; git_log = subprocess.run(['git', '-C', str(PROJECT_ROOT), 'log', '--oneline'], capture_output=True, text=True, encoding='utf-8', errors='replace').stdout
    commit_count = len([l for l in git_log.splitlines() if l.strip()])
    d7_score = min(1.0, commit_count / 5)  # 至少 5 次提交满分
    print(f"\n[GIT] D7 Git 提交健康度: {d7_score:.0%} ({commit_count} 次提交)")
    if commit_count == 0:
        print("   [FAIL] 无 Git 提交记录")

    # --- D8: 断链检测 ---
    broken = find_broken_wikilinks()
    total_md = fm["total"]
    d8_score = 1.0 - (len(broken) / max(total_md, 1))
    print(f"\n[LINK] D8 悬空链接率: {1-d8_score:.1%} ({len(broken)} 个断链)")
    if broken:
        for b in broken[:5]:
            print(f"   [WARN]  {b['file']}  [[{b['link']}]]")
        if len(broken) > 5:
            print(f"   ... 还有 {len(broken)-5} 个")

    # --- D9: 文件总览统计 ---
    line_stats = count_file_lines()
    total_lines = sum(line_stats.values())
    md_files = {k: v for k, v in line_stats.items() if k.endswith(".md")}
    py_files = {k: v for k, v in line_stats.items() if k.endswith(".py")}
    total_md_files = len(md_files)
    total_py_files = len(py_files)
    d9_score = min(1.0, total_md_files / 8)  # 至少 8 个 md 文件满分
    print(f"\n[STATS] D9 项目规模: {d9_score:.0%}")
    print(f"   Markdown 文件: {total_md_files} 个 ({sum(md_files.values())} 行)")
    print(f"   Python 脚本: {total_py_files} 个 ({sum(py_files.values())} 行)")
    print(f"   总文件数: {len(line_stats)} 个 ({total_lines} 行)")

    # --- D10: 版本标记 ---
    tags = subprocess.run(['git', '-C', str(PROJECT_ROOT), 'tag'], capture_output=True, text=True, encoding='utf-8', errors='replace').stdout.strip()
    has_tag = bool(tags)
    d10_score = 1.0 if has_tag else 0.0
    print(f"\n[FM]  D10 版本标记: {d10_score:.0%}")
    print(f"   {'[OK] 已打标签: ' + tags if has_tag else '[FAIL] 无版本标签'}")

    # --- Python 语法检查 ---
    import ast as _ast
    py_errors = []
    for f in sorted(PROJECT_ROOT.rglob("*.py")):
        if ".git" in str(f):
            continue
        try:
            source = f.read_text(encoding='utf-8', errors='ignore')
            _ast.parse(source)
        except SyntaxError as e:
            py_errors.append(f"{f.relative_to(PROJECT_ROOT).as_posix()}: {e}")
    d11_score = 1.0 - (len(py_errors) / max(total_py_files, 1))
    print(f"\n[PY] D11 Python 语法健康: {d11_score:.0%}")
    if py_errors:
        for f in py_errors:
            print(f"   [FAIL] 语法错误: {f}")
    else:
        print("   [OK] 全部脚本语法检查通过")

    # --- 综合评分 ---
    scores = {
        "D1_文件结构完整性": d1_score,
        "D2_宪法段落完整性": d2_score,
        "D3_Frontmatter覆盖率": d3_score,
        "D4_Profile配置完整性": d4_score,
        "D5_技能文件完整性": d5_score,
        "D6_脚本文件完整性": d6_score,
        "D7_Git提交健康度": d7_score,
        "D8_悬空链接率(越低越好)": 1 - d8_score,
        "D9_项目规模": d9_score,
        "D10_版本标记": d10_score,
        "D11_Python语法健康": d11_score,
    }

    print("\n" + "=" * 60)
    print("  [STATS] 综合评分")
    print("=" * 60)
    all_pass = True
    for name, score in scores.items():
        status = "[OK]" if score >= 0.85 else "[FAIL]"
        if score < 0.85:
            all_pass = False
        print(f"  {status} {name}: {score:.1%}")

    print("\n" + "=" * 60)
    if all_pass:
        print("  [ALL OK] 全部维度达标")
    else:
        print("  [WARN]  部分维度未达标请检查上述 [FAIL] 项")
    print(f"  审计耗时: {(datetime.now() - start_time).total_seconds():.1f}s")
    print("=" * 60)

    return {
        "timestamp": start_time.isoformat(),
        "scores": scores,
        "all_pass": all_pass,
        "issues": {
            "dir_missing": dir_issues,
            "missing_sections": all_missing,
            "missing_frontmatter": fm["files"],
            "broken_links": broken[:20],
            "python_errors": py_errors,
        }
    }


def main():
    parser = argparse.ArgumentParser(description="ECO AGENT 质量审计")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    parser.add_argument("--summary", action="store_true", help="仅输出摘要")
    args = parser.parse_args()

    result = audit_project_quality()

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))

    if args.summary:
        scores = result["scores"]
        avg = sum(scores.values()) / len(scores)
        print(f"\n平均分: {avg:.1%} | 全部达标: {'是' if result['all_pass'] else '否'}")


if __name__ == "__main__":
    main()
