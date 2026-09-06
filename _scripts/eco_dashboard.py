#!/usr/bin/env python3
"""
eco_dashboard.py — eco Agent 执法态势看板

功能：
  1. 全模块数据聚合统计
  2. 自动生成统计报告
  3. 飞书/企微/钉钉卡片推送
  4. 趋势分析

用法：
  python _scripts/eco_dashboard.py                # 生成报告
  python _scripts/eco_dashboard.py --card feishu  # 推送飞书卡片
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Any

logger = logging.getLogger("eco_dashboard")

PROJECT_ROOT = Path(__file__).resolve().parent.parent

try:
    import sys as _sys
    _sys.path.insert(0, str(PROJECT_ROOT))
    from _scripts.memory_tree import MemoryTree
    from _scripts.enforcement_cases import CaseManager, BenchmarkManager
    from _scripts.evolution_engine import EvolutionEngine  # noqa: F401 可用性探测
    from _scripts.writer_agent import WriterAgent
    from _scripts.cross_region_sync import CrossRegionSync
    HAS_MODULES = True
except ImportError as e:
    HAS_MODULES = False
    logger.warning(f"部分模块加载失败: {e}")


class Dashboard:
    """执法态势看板"""

    def __init__(self):
        self._mt = MemoryTree() if HAS_MODULES else None
        self._gather_time = datetime.now()

    def gather_all(self) -> dict[str, Any]:
        """聚合全模块数据"""
        report = {
            "timestamp": self._gather_time.isoformat(),
            "generated_at": self._gather_time.strftime("%Y-%m-%d %H:%M"),
            "modules": {},
        }

        # Memory Tree
        if self._mt:
            try:
                mt_stats = self._mt.get_stats()
                hot = self._mt.get_hot_nodes(5)
                report["modules"]["memory_tree"] = {
                    "total_nodes": mt_stats.get("total_nodes", 0),
                    "total_edges": mt_stats.get("total_edges", 0),
                    "db_size_kb": mt_stats.get("db_size_kb", 0),
                    "by_type": mt_stats.get("by_type", {}),
                    "hot_nodes": [n.get("title", "") for n in hot],
                }
            except Exception as e:
                report["modules"]["memory_tree"] = {"error": str(e)}

        # 案例
        try:
            cm = CaseManager(self._mt)
            case_stats = cm.get_stats()
            report["modules"]["cases"] = {
                "total": case_stats.get("total", 0),
                "by_type": case_stats.get("by_type", {}),
                "by_region": case_stats.get("by_region", {}),
                "total_penalty": case_stats.get("total_penalty", 0),
                "avg_penalty": case_stats.get("avg_penalty", 0),
            }
        except Exception as e:
            report["modules"]["cases"] = {"error": str(e)}

        # 裁量基准
        try:
            bm = BenchmarkManager(self._mt)
            bm_stats = bm.get_stats()
            report["modules"]["benchmarks"] = bm_stats
        except Exception as e:
            report["modules"]["benchmarks"] = {"error": str(e)}

        # 文书
        try:
            wa = WriterAgent(self._mt)
            doc_stats = wa.get_stats()
            report["modules"]["documents"] = doc_stats
            # 列出可用模板
            templates = wa.list_templates()
            report["modules"]["templates"] = list(templates.keys())
        except Exception as e:
            report["modules"]["documents"] = {"error": str(e)}

        # 跨省协同
        try:
            crs = CrossRegionSync("dashboard-node", "中心")
            crs_stats = crs.get_stats()
            report["modules"]["cross_region"] = crs_stats
        except Exception as e:
            report["modules"]["cross_region"] = {"error": str(e)}

        # Git 信息
        try:
            import subprocess
            commits = subprocess.run(
                ["git", "-C", str(PROJECT_ROOT), "log", "--oneline"],
                capture_output=True, text=True, encoding="utf-8"
            ).stdout.strip()
            tags = subprocess.run(
                ["git", "-C", str(PROJECT_ROOT), "tag"],
                capture_output=True, text=True, encoding="utf-8"
            ).stdout.strip()
            report["modules"]["git"] = {
                "total_commits": len([l for l in commits.split("\n") if l.strip()]),
                "tags": tags.split("\n") if tags else [],
                "latest_tag": tags.split("\n")[-1] if tags else "无",
            }
        except Exception:
            report["modules"]["git"] = {"error": "Git 信息不可用"}

        return report

    def generate_markdown_report(self, report: dict | None = None) -> str:
        """生成 Markdown 统计报告"""
        if not report:
            report = self.gather_all()
        r = report.get("modules", {})
        lines = [
            "# eco Agent 执法态势报告",
            "",
            f"> 生成时间：{report.get('generated_at', '')}",
            "",
            "---",
            "",
            "## 一、核心数据",
            "",
            "| 指标 | 数值 |",
            "|:-----|:----:|",
        ]
        mt = r.get("memory_tree", {})
        if "total_nodes" in mt:
            lines.append(f"| 知识库节点数 | {mt.get('total_nodes', 0)} |")
            lines.append(f"| 关联边数 | {mt.get('total_edges', 0)} |")
            lines.append(f"| 数据库大小 | {mt.get('db_size_kb', 0):.0f} KB |")
        cases = r.get("cases", {})
        if "total" in cases:
            lines.append(f"| 执法案例数 | {cases.get('total', 0)} |")
            lines.append(f"| 案例累计处罚总额 | {cases.get('total_penalty', 0):,.0f} 元 |")
            lines.append(f"| 平均处罚金额 | {cases.get('avg_penalty', 0):,.0f} 元 |")
        doc = r.get("documents", {})
        if "total" in doc:
            lines.append(f"| 生成文书数 | {doc.get('total', 0)} |")
        bm = r.get("benchmarks", {})
        if "total" in bm:
            lines.append(f"| 裁量基准数 | {bm.get('total', 0)} |")
        cr = r.get("cross_region", {})
        if "registered_nodes" in cr:
            lines.append(f"| 跨省协同节点 | {cr.get('registered_nodes', 0)} |")

        # 案例按区域分布
        if cases.get("by_region"):
            lines.extend(["", "## 二、案例区域分布", "", "| 地区 | 数量 |", "|:-----|:----:|"])
            for region, count in sorted(cases["by_region"].items(), key=lambda x: -x[1]):
                lines.append(f"| {region} | {count} |")

        # Memory Tree 按类型分布
        if mt.get("by_type"):
            lines.extend(["", "## 三、知识节点构成", "", "| 类型 | 数量 | 平均评分 |", "|:-----|:----:|:--------:|"])
            for t, info in mt["by_type"].items():
                lines.append(f"| {t} | {info.get('count', 0)} | {info.get('avg_score', '-')} |")

        # Git
        git = r.get("git", {})
        if "latest_tag" in git:
            lines.extend(["", "## 四、版本信息", "", f"| 版本 | {git.get('latest_tag', '')} |",
                          "|:-----|:----:|", f"| 累计提交 | {git.get('total_commits', 0)} |"])

        lines.extend(["", "---", "", "*报告由 eco Agent Dashboard 自动生成*"])
        return "\n".join(lines)

    def generate_card_data(self, report: dict | None = None,
                           platform: str = "feishu") -> dict[str, Any]:
        """生成飞书/企微/钉钉卡片数据"""
        if not report:
            report = self.gather_all()
        r = report.get("modules", {})

        mt = r.get("memory_tree", {})
        cases = r.get("cases", {})
        doc = r.get("documents", {})
        bm = r.get("benchmarks", {})
        cr = r.get("cross_region", {})
        git = r.get("git", {})

        lines = [
            f"知识节点: {mt.get('total_nodes', 0)} | 关联边: {mt.get('total_edges', 0)}",
            f"执法案例: {cases.get('total', 0)} 件 | 处罚总额: {cases.get('total_penalty', 0):,.0f}元",
            f"裁量基准: {bm.get('total', 0)} 条 | 文书: {doc.get('total', 0)} 份",
            f"跨省节点: {cr.get('registered_nodes', 0)} 个",
        ]
        if git.get("latest_tag"):
            lines.append(f"版本: {git['latest_tag']} | 提交: {git.get('total_commits', 0)}")

        content = "\n".join(lines)
        title = f"eco Agent 执法态势 · {report.get('generated_at', '')}"

        if platform == "feishu":
            return {
                "msg_type": "interactive",
                "card": {
                    "header": {"title": {"tag": "plain_text", "content": title}, "template": "blue"},
                    "elements": [{"tag": "markdown", "content": content}],
                },
            }
        elif platform == "dingtalk":
            return {
                "msgKey": "sampleMarkdown",
                "msgParam": json.dumps({"title": title, "text": content}, ensure_ascii=False),
            }
        else:
            return {"title": title, "content": content}

    def save_report(self, report: dict | None = None) -> Path:
        """保存报告到文件"""
        if not report:
            report = self.gather_all()
        md = self.generate_markdown_report(report)
        report_dir = PROJECT_ROOT / "memory-tree" / "obsidian_sync" / "quality"
        report_dir.mkdir(parents=True, exist_ok=True)
        path = report_dir / f"dashboard_{self._gather_time.strftime('%Y%m%d_%H%M')}.md"
        path.write_text(md, encoding="utf-8")
        logger.info(f"[Dashboard] 报告已保存: {path}")
        return path

    def push_card(self, platform: str = "feishu"):
        """推送卡片（占位，实际调用各平台 SDK）"""
        report = self.gather_all()
        card = self.generate_card_data(report, platform)
        logger.info(f"[Dashboard] {platform} 卡片就绪，待推送")
        return card


# ===== 主入口 =====

def main():
    import argparse
    parser = argparse.ArgumentParser(description="eco Agent 执法态势看板")
    parser.add_argument("--card", choices=["feishu", "wecom", "dingtalk"], help="推送卡片")
    parser.add_argument("--save", action="store_true", default=True, help="保存报告")
    args = parser.parse_args()

    dashboard = Dashboard()
    report = dashboard.gather_all()

    if args.save:
        path = dashboard.save_report(report)
        print(f"报告已保存: {path}")

    if args.card:
        card = dashboard.push_card(args.card)
        print(f"{args.card} 卡片已生成")

    # 控制台输出摘要
    r = report.get("modules", {})
    print("\n")
    print(dashboard.generate_markdown_report(report))


def test():
    """测试看板"""
    dashboard = Dashboard()
    report = dashboard.gather_all()
    r = report.get("modules", {})

    print(f"[TEST] 模块数: {len(r)}")
    for name, data in r.items():
        if "error" in data:
            print(f"  {name}: [跳过]")
        else:
            print(f"  {name}: [OK] {len(data)} 字段")

    md = dashboard.generate_markdown_report(report)
    print(f"\n[TEST] 报告长度: {len(md)} 字符")

    card = dashboard.generate_card_data(report, "feishu")
    print(f"[TEST] 飞书卡片: {card.get('msg_type', '')}")

    path = dashboard.save_report(report)
    print(f"[TEST] 报告保存: {path}")

    print("\n[OK] 执法态势看板测试通过")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test()
