#!/usr/bin/env python3
"""
subconscious_watcher.py — ECO AGENT 法规时效监控模块（Subconscious）

后台循环：定时检查法规时效状态 → 自动更新知识图谱 → 推送通知 → 影响评估

用法：
  # 一次性检查
  python _scripts/subconscious_watcher.py --check

  # 启动后台监控守护
  python _scripts/subconscious_watcher.py --daemon --interval 3600

  # 生成报告
  python _scripts/subconscious_watcher.py --report
"""

import os
import sys
import json
import re
import time
import logging
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

logger = logging.getLogger("subconscious_watcher")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALERTS_DIR = PROJECT_ROOT / "memory-tree" / "obsidian_sync" / "alerts"
ALERTS_DIR.mkdir(parents=True, exist_ok=True)

# ===== 法规时效数据库 =====

# 2026 年关键法规时效节点
STATUTE_REGISTRY = {
    "生态环境法典": {
        "status": "现行",
        "effective": "2026-08-15",
        "category": "法典",
        "notes": "第 1242 号国务院令，废止 10 部单行法",
    },
    "环境保护法": {
        "status": "已废止",
        "effective": "2026-08-15",
        "repealed_by": "生态环境法典",
        "category": "综合",
    },
    "环境影响评价法": {
        "status": "已废止",
        "effective": "2026-08-15",
        "absorbed_by": "生态环境法典第一编·第五章",
        "category": "综合",
    },
    "海洋环境保护法": {
        "status": "已废止",
        "effective": "2026-08-15",
        "absorbed_by": "生态环境法典",
        "category": "海洋",
    },
    "大气污染防治法": {
        "status": "已废止",
        "effective": "2026-08-15",
        "absorbed_by": "生态环境法典第二编·第二分编",
        "category": "大气",
    },
    "水污染防治法": {
        "status": "已废止",
        "effective": "2026-08-15",
        "absorbed_by": "生态环境法典第二编·第三分编",
        "category": "水",
    },
    "土壤污染防治法": {
        "status": "已废止",
        "effective": "2026-08-15",
        "absorbed_by": "生态环境法典第二编·第五分编",
        "category": "土壤",
    },
    "固体废物污染环境防治法": {
        "status": "已废止",
        "effective": "2026-08-15",
        "absorbed_by": "生态环境法典第二编·第六分编",
        "category": "固废",
    },
    "噪声污染防治法": {
        "status": "已废止",
        "effective": "2026-08-15",
        "absorbed_by": "生态环境法典第二编·第七分编",
        "category": "噪声",
    },
    "放射性污染防治法": {
        "status": "已废止",
        "effective": "2026-08-15",
        "absorbed_by": "生态环境法典第二编·第八分编",
        "category": "放射性",
    },
    "清洁生产促进法": {
        "status": "已废止",
        "effective": "2026-08-15",
        "absorbed_by": "生态环境法典第四编·第二章",
        "category": "清洁生产",
    },
}


class StatuteWatcher:
    """法规时效监控器"""

    def __init__(self, memory_tree=None):
        self._mt = memory_tree
        self._registry = dict(STATUTE_REGISTRY)
        self._history: List[Dict[str, Any]] = []
        self._alert_count = 0

    # ═══════════════════════════════════
    # 检查
    # ═══════════════════════════════════

    def check_all(self) -> Dict[str, Any]:
        """执行全面检查"""
        now = datetime.now()
        results = {
            "timestamp": now.isoformat(),
            "total_statutes": len(self._registry),
            "changes": [],
            "alerts": [],
            "stats": {},
        }

        for statute_name, info in self._registry.items():
            check = self._check_statute(statute_name, info, now)
            if check:
                results["changes"].append(check)
                if check.get("alert"):
                    results["alerts"].append(check)
                    self._alert_count += 1

        # 统计
        status_counts = {}
        for info in self._registry.values():
            s = info.get("status", "未知")
            status_counts[s] = status_counts.get(s, 0) + 1
        results["stats"] = status_counts
        results["alert_count"] = len(results["alerts"])

        self._history.append(results)
        logger.info(f"[Watcher] 法规检查完成: {results['total_statutes']} 部, "
                    f"{results['alert_count']} 项告警")
        return results

    def _check_statute(self, name: str, info: Dict[str, Any],
                       now: datetime) -> Optional[Dict[str, Any]]:
        """检查单部法规"""
        effective_str = info.get("effective")
        if not effective_str:
            return None

        try:
            effective_date = datetime.fromisoformat(effective_str)
        except ValueError:
            return None

        days_until = (effective_date - now).days
        days_since = (now - effective_date).days

        check = {
            "statute": name,
            "status": info.get("status", ""),
            "category": info.get("category", ""),
            "effective_date": effective_str,
            "days_until_effective": days_until if days_until > 0 else 0,
            "days_since_effective": days_since if days_since > 0 else 0,
            "alert": False,
            "alert_level": None,
            "alert_message": None,
        }

        # 告警规则
        if days_since >= 0 and days_since <= 7 and info.get("status") == "现行":
            check["alert"] = True
            check["alert_level"] = "info"
            check["alert_message"] = f"法规 '{name}' 今日起生效"
        elif days_until > 0 and days_until <= 30 and info.get("status") == "现行":
            check["alert"] = True
            check["alert_level"] = "info"
            check["alert_message"] = f"法规 '{name}' 将在 {days_until} 天后生效"
        elif days_since > 0 and info.get("status") == "已废止":
            check["alert"] = True
            check["alert_level"] = "warning"
            check["alert_message"] = f"法规 '{name}' 已于 {days_since} 天前废止"
            if "absorbed_by" in info:
                check["alert_message"] += f"，内容已由 {info['absorbed_by']} 吸收"

        return check

    # ═══════════════════════════════════
    # 更新
    # ═══════════════════════════════════

    def update_statute(self, name: str, updates: Dict[str, Any]) -> bool:
        """更新法规信息"""
        if name not in self._registry:
            self._registry[name] = {}
        self._registry[name].update(updates)
        self._registry[name]["updated_at"] = datetime.now().isoformat()
        logger.info(f"[Watcher] 法规已更新: {name}")
        return True

    def add_statute(self, name: str, info: Dict[str, Any]) -> bool:
        """新增法规"""
        if name in self._registry:
            return False
        self._registry[name] = info
        logger.info(f"[Watcher] 新增法规: {name}")
        return True

    # ═══════════════════════════════════
    # 报告
    # ═══════════════════════════════════

    def generate_report(self, check_result: Optional[Dict[str, Any]] = None
                        ) -> str:
        """生成法规时效报告"""
        if not check_result:
            check_result = self.check_all()

        lines = [
            "# 法规时效监控报告",
            "",
            f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"> 监控法规：{check_result['total_statutes']} 部",
            f"> 本次告警：{check_result['alert_count']} 项",
            "",
            "---",
            "",
            "## 状态分布",
            "",
            "| 状态 | 数量 |",
            "|:-----|:----:|",
        ]

        for status, count in check_result["stats"].items():
            lines.append(f"| {status} | {count} |")

        if check_result["alerts"]:
            lines.extend(["", "---", "", "## 告警详情", ""])
            for alert in check_result["alerts"]:
                icon = {"warning": "🔴", "info": "🟡", "error": "🔴"}.get(
                    alert.get("alert_level", ""), "⚪")
                lines.append(f"### {icon} {alert['statute']}")
                lines.append(f"")
                lines.append(f"- **状态**：{alert['status']}")
                lines.append(f"- **生效日期**：{alert['effective_date']}")
                lines.append(f"- **告警**：{alert['alert_message']}")
                if alert.get("days_since_effective"):
                    lines.append(f"- **已生效 {alert['days_since_effective']} 天**")
                lines.append("")

        lines.extend([
            "---",
            "",
            "## 全部法规清单",
            "",
            "| 法规名称 | 状态 | 生效日期 | 备注 |",
            "|:---------|:----:|:---------|:------|",
        ])

        for name, info in sorted(self._registry.items()):
            notes = info.get("absorbed_by") or info.get("notes", "")
            lines.append(
                f"| {name} | {info.get('status', '')} "
                f"| {info.get('effective', '')} | {notes[:30]} |"
            )

        return "\n".join(lines)

    # ═══════════════════════════════════
    # 后台循环
    # ═══════════════════════════════════

    def daemon_loop(self, interval: int = 3600, max_cycles: int = 0):
        """后台守护循环"""
        cycle = 0
        logger.info(f"[Watcher] 后台监控启动 (间隔 {interval}s)")

        try:
            while True:
                cycle += 1
                if max_cycles and cycle > max_cycles:
                    break

                now = datetime.now()
                logger.info(f"[Watcher] 第 {cycle} 次检查...")

                # 执行检查
                result = self.check_all()

                # 如果有告警，写入文件
                if result["alert_count"] > 0:
                    report = self.generate_report(result)
                    report_path = ALERTS_DIR / f"report_{now.strftime('%Y%m%d_%H%M')}.md"
                    report_path.write_text(report, encoding="utf-8")

                    # 同步到 Memory Tree
                    if self._mt:
                        for alert in result["alerts"]:
                            try:
                                self._mt.create_node(
                                    type="alert",
                                    title=alert["statute"],
                                    content=json.dumps(alert, ensure_ascii=False),
                                    tags=["statute_watch", alert.get("alert_level", "info")],
                                    score=80.0,
                                    source="system",
                                )
                            except Exception:
                                pass

                    logger.info(f"[Watcher] {result['alert_count']} 项告警已记录")

                # 等待下一个周期
                if max_cycles and cycle >= max_cycles:
                    break
                logger.info(f"[Watcher] 等待 {interval}s 后下次检查...")
                time.sleep(interval)

        except KeyboardInterrupt:
            logger.info("[Watcher] 后台监控已停止")

    # ═══════════════════════════════════
    # 影响评估
    # ═══════════════════════════════════

    def impact_assessment(self, statute_name: str) -> Dict[str, Any]:
        """评估法规变更的影响"""
        info = self._registry.get(statute_name)
        if not info:
            return {"error": f"未找到法规: {statute_name}"}

        assessment = {
            "statute": statute_name,
            "status": info.get("status", ""),
            "effective": info.get("effective", ""),
            "impacts": [],
            "recommendations": [],
        }

        if info.get("status") == "已废止":
            absorbed = info.get("absorbed_by", "")
            assessment["impacts"].append({
                "area": "法规引用",
                "impact": "高",
                "description": f"该法规已废止，所有引用需改为 {absorbed}",
            })
            assessment["impacts"].append({
                "area": "执法文书",
                "impact": "高",
                "description": "已有文书中引用该法规的条款需要更新",
            })
            assessment["impacts"].append({
                "area": "裁量基准",
                "impact": "中",
                "description": "对应的裁量基准可能需要调整",
            })
            assessment["recommendations"].extend([
                f"更新知识库中所有引用 {statute_name} 的条目",
                f"检查执法文书中对 {statute_name} 的引用",
                "通知相关执法人员法规变更情况",
            ])

        if info.get("status") == "现行":
            assessment["recommendations"].append(
                f"确认 {statute_name} 现行有效，继续监控更新情况"
            )

        return assessment


# ===== 测试 =====

def test():
    """测试法规监控模块"""
    print("[TEST] 法规时效监控检查...")
    watcher = StatuteWatcher()
    result = watcher.check_all()

    print(f"  法规总数: {result['total_statutes']}")
    print(f"  当前告警: {result['alert_count']} 项")

    for alert in result["alerts"]:
        print(f"    [{alert['alert_level']}] {alert['statute']}: {alert['alert_message']}")

    # 生成报告
    report = watcher.generate_report(result)
    report_lines = report.split("\n")
    print(f"\n[TEST] 报告生成: {len(report_lines)} 行")

    # 影响评估
    assessment = watcher.impact_assessment("大气污染防治法")
    print(f"\n[TEST] 影响评估: {assessment['statute']}")
    print(f"  Impacts: {len(assessment['impacts'])} 项")
    print(f"  Recommendations: {len(assessment['recommendations'])} 项")

    # 验证数据
    assert result["total_statutes"] == 11, "应含 11 部法规"
    assert len(result["alerts"]) > 0, "应有至少 1 项告警（已废止法规）"
    print("\n[OK] 法规监控模块测试通过")


def main():
    parser = argparse.ArgumentParser(description="ECO AGENT 法规时效监控")
    parser.add_argument("--check", action="store_true", help="执行一次性检查")
    parser.add_argument("--daemon", action="store_true", help="启动后台守护")
    parser.add_argument("--interval", type=int, default=3600, help="检查间隔（秒）")
    parser.add_argument("--report", action="store_true", help="生成报告")
    parser.add_argument("--impact", type=str, help="评估指定法规的影响")
    args = parser.parse_args()

    from _scripts.memory_tree import MemoryTree
    mt = MemoryTree()
    watcher = StatuteWatcher(mt)

    if args.check:
        result = watcher.check_all()
        print(f"检查完成: {result['total_statutes']} 部, {result['alert_count']} 项告警")
        for alert in result["alerts"]:
            print(f"  [{alert['alert_level']}] {alert['statute']}: {alert['alert_message']}")

    elif args.daemon:
        watcher.daemon_loop(interval=args.interval)

    elif args.report:
        result = watcher.check_all()
        report = watcher.generate_report(result)
        report_path = ALERTS_DIR / f"report_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
        report_path.write_text(report, encoding="utf-8")
        print(f"报告已生成: {report_path}")

    elif args.impact:
        assessment = watcher.impact_assessment(args.impact)
        print(json.dumps(assessment, ensure_ascii=False, indent=2))

    else:
        parser.print_help()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test()
