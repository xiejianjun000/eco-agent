#!/usr/bin/env python3
"""
Eco Agent 并行测试执行器

用法：
  python tests/run_all.py                    # 全量并行测试
  python tests/run_all.py --quick            # 快速模式（每个模块只跑1个用例）
  python tests/run_all.py --ci               # CI 模式（输出 JUnit XML）
  python tests/run_all.py --report-only       # 仅重新生成报告（不跑测试）
"""

import os, sys, json, time, subprocess, glob, re
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = ROOT / "tests" / "reports"
TEST_MODULES_DIR = ROOT / "tests" / "modules"
REPORT_DIR.mkdir(parents=True, exist_ok=True)


def discover_tests():
    """发现所有测试文件"""
    files = sorted(TEST_MODULES_DIR.glob("test_*.py"))
    modules = {}
    for f in files:
        # 解析测试类和方法
        content = f.read_text("utf-8", errors="replace")
        classes = re.findall(r'class\s+(\w+)\s*:', content)
        methods = re.findall(r'def\s+(test_\w+)\s*\(', content)
        modules[f.stem] = {"file": str(f), "classes": classes, "methods": methods}
    return modules


def run_pytest(args: list = None) -> dict:
    """运行 pytest 并捕获结果"""
    cmd = ["python3", "-m", "pytest"]
    if args:
        cmd.extend(args)

    # 默认参数
    cmd.extend([
        "-v",
        "--tb=short",
        "-p", "no:cacheprovider",
        str(TEST_MODULES_DIR),
    ])

    start = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=str(ROOT))
    elapsed = time.time() - start

    # 解析结果
    passed = failed = skipped = errors = 0
    last_line = ""
    for line in result.stdout.split("\n"):
        if "passed" in line and "failed" in line:
            last_line = line
    if last_line:
        m = re.search(r"(\d+)\s+passed", last_line)
        if m: passed = int(m.group(1))
        m = re.search(r"(\d+)\s+failed", last_line)
        if m: failed = int(m.group(1))
        m = re.search(r"(\d+)\s+skipped", last_line)
        if m: skipped = int(m.group(1))
    # 如果解析失败，从"="行提取
    if passed == 0 and failed == 0:
        for line in result.stdout.split("\n"):
            m = re.match(r"=+\s*(\d+)\s+passed", line)
            if m: passed = int(m.group(1))
            m = re.match(r"=+\s*(\d+)\s+failed", line)
            if m: failed = int(m.group(1))

    return {
        "passed": passed, "failed": failed, "skipped": skipped, "errors": errors,
        "elapsed_s": round(elapsed, 2),
        "stdout": result.stdout[-3000:] if len(result.stdout) > 3000 else result.stdout,
        "stderr": result.stderr[-1000:] if len(result.stderr) > 1000 else result.stderr,
    }


def generate_report(results: dict, modules: dict) -> str:
    """生成测试报告 Markdown"""
    timestamp = datetime.now()
    total = results["passed"] + results["failed"] + results["skipped"] + results["errors"]
    pass_rate = round(results["passed"] / max(total, 1) * 100, 1)

    report = [
        f"# Eco Agent 测试报告",
        f"",
        f"> **运行时间**: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
        f"> **运行耗时**: {results['elapsed_s']}s",
        f"> **测试模式**: 并行 pytest",
        f"",
        f"## 汇总",
        f"",
        f"| 指标 | 数值 |",
        f"|:-----|:----:|",
        f"| 总用例 | {total} |",
        f"| ✅ 通过 | {results['passed']} |",
        f"| ❌ 失败 | {results['failed']} |",
        f"| ⏭ 跳过 | {results['skipped']} |",
        f"| ⚠ 错误 | {results['errors']} |",
        f"| **通过率** | **{pass_rate}%** |",
        f"",
        f"## 模块详情",
        f"",
    ]

    for mod_name, info in modules.items():
        mcount = len(info["methods"])
        report.append(f"- **{mod_name}**: {mcount} 个测试 ({', '.join(info['classes'])})")

    report.extend(["", "## 执行输出", "", "```"])
    report.append(results["stdout"][-2000:])
    report.append("```")

    if results["stderr"]:
        report.extend(["", "## 错误输出", "", "```"])
        report.append(results["stderr"][-1000:])
        report.append("```")

    return "\n".join(report)


def update_readme_badge(pass_rate: float, total: int):
    """更新 README 中的测试徽章"""
    readme_path = ROOT / "README.md"
    if not readme_path.exists():
        return

    content = readme_path.read_text("utf-8", errors="replace")
    color = "brightgreen" if pass_rate >= 95 else "yellow" if pass_rate >= 80 else "red"

    new_badges = (
        f"[![Tests](https://img.shields.io/badge/tests-{total}%20passed-{color})](TEST_LOG.md)"
    )

    # Replace or insert badges
    badge_pattern = r"\[!\[Tests\].*?\]\(TEST_LOG\.md\)"
    if re.search(badge_pattern, content):
        content = re.sub(badge_pattern, new_badges, content)
    else:
        # Insert after the first badge line
        lines = content.split("\n")
        for i, line in enumerate(lines):
            if "[![Version]" in line or "[![License]" in line:
                lines.insert(i + 1, new_badges)
                break
        content = "\n".join(lines)

    readme_path.write_text(content, encoding="utf-8")


def update_test_log(results: dict, report_file: str):
    """累计记录到 TEST_LOG.md"""
    log_path = ROOT / "TEST_LOG.md"
    timestamp = datetime.now()
    total = results["passed"] + results["failed"] + results["skipped"] + results["errors"]
    pass_rate = round(results["passed"] / max(total, 1) * 100, 1)

    entry = f"""## [{timestamp.strftime('%Y-%m-%d %H:%M')}] 测试运行 #{count_entries(log_path) + 1}

| 指标 | 数值 |
|:-----|:----:|
| 总用例 | {total} |
| 通过 | {results['passed']} |
| 失败 | {results['failed']} |
| 跳过 | {results['skipped']} |
| 通过率 | {pass_rate}% |
| 耗时 | {results['elapsed_s']}s |
| 报告 | [{report_file.name}](reports/{report_file.name}) |

---
"""

    if log_path.exists():
        existing = log_path.read_text("utf-8", errors="replace")
        # Insert after header
        parts = existing.split("\n---\n", 1)
        if len(parts) > 1:
            content = parts[0] + "\n---\n" + entry + parts[1]
        else:
            content = existing + "\n" + entry
    else:
        content = f"# Eco Agent 测试日志\n\n> 累计记录所有测试运行历史。\n\n{entry}"

    log_path.write_text(content, encoding="utf-8")


def count_entries(log_path: Path) -> int:
    if not log_path.exists():
        return 0
    content = log_path.read_text("utf-8", errors="replace")
    return content.count("## [")



def main():
    import argparse
    parser = argparse.ArgumentParser(description="Eco Agent 并行测试执行器")
    parser.add_argument("--quick", action="store_true", help="快速模式")
    parser.add_argument("--ci", action="store_true", help="CI 模式")
    parser.add_argument("--report-only", action="store_true", help="仅重新生成报告")
    args = parser.parse_args()

    modules = discover_tests()
    total_methods = sum(len(m["methods"]) for m in modules.values())
    print(f"[Harness] 发现 {len(modules)} 个模块, {total_methods} 个测试用例")

    if args.report_only:
        print("[Harness] 报告只读模式")
        return

    # 运行测试（并行）
    pytest_args = ["-x"] if args.quick else ["-n", "auto"]
    results = run_pytest(pytest_args)

    # 生成报告
    report_md = generate_report(results, modules)
    report_file = REPORT_DIR / f"report_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
    report_file.write_text(report_md, encoding="utf-8")

    # 更新 README 徽章
    total = results["passed"] + results["failed"]
    pass_rate = round(results["passed"] / max(total, 1) * 100, 1)
    update_readme_badge(pass_rate, results["passed"])

    # 更新测试日志
    update_test_log(results, report_file)

    # 打印摘要
    total_all = results["passed"] + results["failed"] + results["skipped"] + results["errors"]
    print(f"\n{'='*50}")
    print(f"  Eco Agent 测试完成")
    print(f"  {'='*50}")
    print(f"  总用例: {total_all}")
    print(f"  通过:   {results['passed']}")
    print(f"  失败:   {results['failed']}")
    print(f"  跳过:   {results['skipped']}")
    print(f"  耗时:   {results['elapsed_s']}s")
    print(f"  通过率: {pass_rate}%")
    print(f"  报告:   {report_file}")
    print(f"  {'='*50}")

    if results["failed"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
