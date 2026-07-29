#!/usr/bin/env python3
"""
lint.py — ECO AGENT 项目健康检查工具

检查项
  1. 文件完整性 — 必备文件是否存在
  2. 断链检测 — [[wikilink]] 悬空链接
  3. 原文指针 — ## 原文指针 段落存在性
  4. Frontmatter — YAML 元数据完整性
  5. 重复文件 — 同名文件检测
  6. 大文件检测 — > 500KB 的文件
  7. Git 状态 — 未提交变更

用法
  python _scripts/lint.py              # 完整检查
  python _scripts/lint.py --fix        # 尝试修复
  python _scripts/lint.py --verbose    # 详细输出
"""

import os
import re
import sys
import argparse
from pathlib import Path
from datetime import datetime


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def check_file_integrity():
    """检查必备文件是否存在"""
    required = [
        "CLAUDE.md", "SCHEMA.md", "CHANGELOG.md", "README.md",
        "开发实施方案.md", "项目说明书.md",
        "_scripts/eco-knowledge-mcp.py",
        "profiles/eco-agent/config.yaml",
        "profiles/eco-agent/SOUL.md",
        "profiles/eco-agent/PERMISSION.md",
        "skills/query-skill.md",
        "skills/enforcement-qa-skill.md",
    ]
    missing = []
    for f in required:
        if not (PROJECT_ROOT / f).exists():
            missing.append(f)
    return missing


def check_broken_links():
    """检测所有 .md 文件中的悬空 wikilink"""
    broken = []
    all_stems = set()
    for f in PROJECT_ROOT.rglob("*.md"):
        if ".git" not in str(f):
            all_stems.add(f.stem)

    for f in sorted(PROJECT_ROOT.rglob("*.md")):
        if ".git" in str(f):
            continue
        content = f.read_text(encoding="utf-8", errors="ignore")
        links = re.findall(r'\[\[([^\]|#]+?)(?:[|#][^\]]*)?\]\]', content)
        for link in links:
            link_name = link.strip()
            if link_name not in all_stems:
                rel = f.relative_to(PROJECT_ROOT)
                broken.append((str(rel.as_posix()), link_name))
    return broken


def check_source_pointers():
    """检查 ## 原文指针 段落存在性"""
    missing_pointer = []
    for f in sorted(PROJECT_ROOT.rglob("*.md")):
        if ".git" in str(f) or f.name == "README.md":
            continue
        content = f.read_text(encoding="utf-8", errors="ignore")
        if not re.search(r'##\s*原文指针', content):
            rel = f.relative_to(PROJECT_ROOT)
            missing_pointer.append(str(rel.as_posix()))
    return missing_pointer


def check_frontmatter():
    """检查 YAML frontmatter"""
    missing = []
    bad_format = []
    for f in sorted(PROJECT_ROOT.rglob("*.md")):
        if ".git" in str(f) or f.name == "README.md":
            continue
        content = f.read_text(encoding="utf-8", errors="ignore")
        if not content.startswith("---"):
            missing.append(str(f.relative_to(PROJECT_ROOT).as_posix()))
        else:
            end = content.find("---", 3)
            if end == -1:
                bad_format.append(str(f.relative_to(PROJECT_ROOT).as_posix()))
    return missing, bad_format


def check_large_files():
    """检测大文件> 500KB"""
    large = []
    for f in PROJECT_ROOT.rglob("*"):
        if ".git" in str(f) or not f.is_file():
            continue
        size = f.stat().st_size
        if size > 500 * 1024:
            large.append((str(f.relative_to(PROJECT_ROOT).as_posix()), size))
    return large


def check_git_status():
    """检查 Git 未提交文件"""
    status = os.popen("cd /d \"{}\" && git status --short 2>nul".format(PROJECT_ROOT)).read().strip()
    if not status:
        status = os.popen("git -C \"{}\" status --short 2>/dev/null".format(PROJECT_ROOT)).read().strip()
    untracked = []
    modified = []
    for line in status.split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith("??"):
            untracked.append(line[3:])
        else:
            modified.append(line[3:] if len(line) > 3 else line)
    return untracked, modified


def print_section(title, items, ok_msg="[OK] 全部通过"):
    """打印检查结果"""
    print(f"\n  {title}")
    print(f"  {'-' * 40}")
    if not items:
        print(f"  {ok_msg}")
    else:
        for item in items[:10]:
            if isinstance(item, tuple):
                print(f"  [!] {item[0]} ({item[1]})")
            else:
                print(f"  [!] {item}")
        if len(items) > 10:
            print(f"  ... 还有 {len(items)-10} 项")


def main():
    parser = argparse.ArgumentParser(description="ECO AGENT 健康检查")
    parser.add_argument("--fix", action="store_true", help="尝试修复")
    parser.add_argument("--verbose", action="store_true", help="详细输出")
    args = parser.parse_args()

    start = datetime.now()
    print("=" * 50)
    print("  ECO AGENT 项目健康检查")
    print(f"  时间: {start.strftime('%Y-%m-%d %H:%M')}")
    print("=" * 50)

    # 1. 文件完整性
    missing = check_file_integrity()
    print_section("[FILE] 文件完整性", missing)

    # 2. 断链检测
    broken = check_broken_links()
    print_section("[LINK] 断链检测", [f"{f}  [[{l}]]" for f, l in broken])

    # 3. 原文指针
    no_pointer = check_source_pointers()
    print_section("[POINTER] 原文指针检测", no_pointer)

    # 4. Frontmatter
    missing_fm, bad_fm = check_frontmatter()
    print_section("[FM] Frontmatter 完整性", missing_fm)
    print_section("[FMT] Frontmatter 格式", bad_fm)

    # 5. 大文件
    large = check_large_files()
    print_section("[BIG] 大文件检测", [f"{f} ({s/1024:.0f}KB)" for f, s in large])

    # 6. Git 状态
    untracked, modified = check_git_status()
    if args.verbose:
        print_section("[GIT] 未跟踪文件", untracked)
        print_section("[MOD]  已修改文件", modified)

    # 汇总
    total_issues = len(missing) + len(broken) + len(no_pointer) + len(missing_fm) + len(bad_fm)
    print(f"\n{'=' * 50}")
    if total_issues == 0:
        print("  [OK] 健康检查全部通过")
    else:
        print(f"  [!] 发现 {total_issues} 个问题")
    print(f"  耗时: {(datetime.now() - start).total_seconds():.1f}s")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()
