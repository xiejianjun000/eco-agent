#!/usr/bin/env python3
"""
longrun_pulse_evolve.py — L3 Pulse 心跳 + L4 Evolve 进化 长时运行实证剧本

目的：为 README 声称的 L3/L4 自动化行为提供可审计的实测证据（或如实证伪）。
纯观察剧本：只调用 agent_core 公开 API 并配置实例属性，不修改任何被测实现。

探测结论（写剧本前对 agent_core 的实证，2026-07-31）：
  L3 Pulse（agent_core/heartbeat.py，PulseLoop）：
    - 5 个内置步骤 step_sync/step_diff/step_rule_engine/step_mem_cron/step_suggestions
      均为占位实现（返回固定字符串或 None），且默认不被注册——
      EcoLoops.start() 只注册了 sync/diff 两个占位 listener。
      本剧本注册全部 5 个内置步骤以观察其真实执行痕迹。
    - 自适应频率确实存在：_adapt_interval() 按上次心跳耗时在 [300s, 1200s] 内伸缩，
      默认 600s。但无"电池模式降频"（README 声称，代码中无电源/电池感知）。
  L4 Evolve（agent_core/meta_evolution.py，MetaEvolution）：
    - run_full_cycle() 五阶段真实可跑，外加阶段 3.5 反思门禁（Generator→Reflector→Curator）。
    - 无自动触发器：全仓未发现"任务完成后"钩子或"每日 02:00"调度接线，
      仅 eco evolution CLI 手动触发。本剧本按 --evolve-every 手动触发，
      日志中如实标注 trigger=script_manual。
    - 报告文件实为 memory-tree/obsidian_sync/quality/evolution_report_v{N}.md
      （README 写作 evolution_report.md，实际带版本号）。
    - 阶段 3"技能生成"只产出计数、不落盘技能文件；阶段 4"记忆固化"返回固定
      dict——两者均无文件级产物，报告中如实标注。
  LLM：本剧本 setdefault ECO_LLM_DISABLE=1，Reflector 对抗质询与元认知分析章节
    走规则降级/跳过，并在报告中标注。

输出（benchmarks/reports/，自动建目录）：
  longrun_YYYYMMDD_HHMMSS.jsonl — 结构化事件流（run_start/heartbeat/evolve_cycle/anomaly/run_end）
  longrun_YYYYMMDD_HHMMSS.md    — Markdown 汇总报告（对齐 docs/验收报告 风格）

用法：
  python benchmarks/longrun_pulse_evolve.py                  # 默认 24h 长时观察
  python benchmarks/longrun_pulse_evolve.py --hours 8
  python benchmarks/longrun_pulse_evolve.py --smoke          # 压缩时序 120s 快速自检
  python benchmarks/longrun_pulse_evolve.py --smoke --seconds 45 --evolve-every 15
"""

import argparse
import json
import os
import signal
import statistics
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 不调用真实 LLM：pulse/evolve 的 LLM 环节（Reflector 质询、元认知叙述）走规则降级
os.environ.setdefault("ECO_LLM_DISABLE", "1")

REPORTS_DIR = Path(__file__).resolve().parent / "reports"
EVOLVE_REPORT_DIR = ROOT / "memory-tree" / "obsidian_sync" / "quality"

# README 声称 vs agent_core 实测对照（探测结论，报告中原样呈现）
CLAIM_VS_OBSERVED = [
    ("L3 心跳节律 5~20 分钟自适应", "已实现", "_adapt_interval() 按上次心跳耗时在 300~1200s 伸缩，默认 600s", "✅"),
    ("L3 电池模式自动降频", "未实现", "代码中无电源/电池感知，_load_aware 仅按心跳耗时调整", "❌"),
    (
        "L3 五个内置步骤全部静默执行",
        "部分实现",
        "5 个 step_* 均为占位实现（固定返回值）；生产接线 EcoLoops.start() 只注册 sync/diff 两个",
        "⚠️",
    ),
    ("L4 每次任务后 / 每日自动触发", "未实现", "无调度器/钩子接线，仅 eco evolution CLI 手动触发", "❌"),
    ("L4 五阶段进化闭环", "已实现", "run_full_cycle() 五阶段 + 阶段3.5 反思门禁可运行", "✅"),
    (
        "L4 输出 evolution_report.md",
        "有出入",
        "实际文件为 evolution_report_v{N}.md（带版本号），位于 memory-tree/obsidian_sync/quality/",
        "⚠️",
    ),
    ("L4 技能生成/优化", "占位实现", "阶段3 只产出计数（generated/optimized），不落盘技能文件", "⚠️"),
    ("L4 记忆固化", "占位实现", "阶段4 返回固定 dict，无文件产物", "⚠️"),
    ("L4 版本快照", "已实现", "快照 skills/ 与 SOUL.md 至 memory-tree/data/versions/v{N}，仅保留最近 3 版", "✅"),
]

STEP_DUTIES = {
    "sync": "数据同步",
    "diff": "差异检测",
    "rule_engine": "规则触发",
    "mem_cron": "内存整理",
    "suggestions": "主动建议",
}


class LongRunObserver:
    """长时运行观察器——包裹 PulseLoop/MetaEvolution 公开 API，记录一切可观察痕迹。"""

    PULSE_STEPS = ["sync", "diff", "rule_engine", "mem_cron", "suggestions"]

    def __init__(
        self,
        duration_s: float,
        smoke: bool = False,
        reports_dir: Path = REPORTS_DIR,
        pulse_interval_s: float | None = None,
        evolve_every_s: float | None = None,
        enable_evolve: bool = True,
    ):
        self.duration_s = duration_s
        self.smoke = smoke
        self.reports_dir = Path(reports_dir)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.pulse_interval_s = pulse_interval_s
        # L4 无自动触发器，只能脚本手动触发：smoke 默认 45s 一次，长时默认 6h 一次
        self.evolve_every_s = evolve_every_s if evolve_every_s is not None else (45 if smoke else 6 * 3600)
        self.enable_evolve = enable_evolve
        self._stop = threading.Event()
        self._sigint = False
        self._lock = threading.Lock()
        self._events: list[dict] = []
        self._jsonl_fh = None
        self._seen_pulses: set[str] = set()
        self._last_interval: float | None = None
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.jsonl_path = self.reports_dir / f"longrun_{stamp}.jsonl"
        self.md_path = self.reports_dir / f"longrun_{stamp}.md"

    # ── 事件记录 ──

    def _emit(self, event: dict):
        event.setdefault("ts", datetime.now().isoformat(timespec="seconds"))
        line = json.dumps(event, ensure_ascii=False)
        with self._lock:
            self._events.append(event)
            if self._jsonl_fh:
                self._jsonl_fh.write(line + "\n")
                self._jsonl_fh.flush()

    def install_sigint_handler(self):
        """CLI 入口调用：SIGINT 时优雅退出（仍会生成汇总报告）"""

        def _handler(signum, frame):
            self._sigint = True
            self._stop.set()

        signal.signal(signal.SIGINT, _handler)

    # ── L3 Pulse 观察 ──

    def _configure_pulse(self, pulse):
        """配置实例属性以压缩时序（smoke）或指定间隔；不改动类实现"""
        if self.smoke:
            pulse._interval = self.pulse_interval_s or 2
            # 同步压缩自适应边界——默认 300s 下限会在首次自适应时把间隔拉回 300s
            pulse._min_interval = 1
            pulse._max_interval = max(5, int(pulse._interval) * 2)
        elif self.pulse_interval_s:
            pulse._interval = self.pulse_interval_s
            pulse._min_interval = min(pulse._min_interval, self.pulse_interval_s)
            pulse._max_interval = max(pulse._max_interval, self.pulse_interval_s)

    def _register_steps(self, pulse):
        """注册全部 5 个内置步骤（生产接线只注册 sync/diff，这里为观察全部接上）"""
        from agent_core.heartbeat import PulseLoop

        for name, fn in [
            ("sync", PulseLoop.step_sync),
            ("diff", PulseLoop.step_diff),
            ("rule_engine", PulseLoop.step_rule_engine),
            ("mem_cron", PulseLoop.step_mem_cron),
            ("suggestions", PulseLoop.step_suggestions),
        ]:
            pulse.register_listener(name, fn)

    def _collect_pulses(self, pulse):
        """从 PulseLoop._pulse_log 增量收集新心跳（该日志是类的真实执行记录）"""
        for entry in pulse._pulse_log:
            pid = entry["id"]
            if pid in self._seen_pulses:
                continue
            self._seen_pulses.add(pid)
            interval = pulse._interval
            adapted_from = (
                self._last_interval if (self._last_interval is not None and interval != self._last_interval) else None
            )
            self._last_interval = interval
            steps = {}
            for name in self.PULSE_STEPS:
                steps[name] = entry["results"].get(name) or {"status": "not_registered"}
                if steps[name].get("status") == "error":
                    self._emit(
                        {
                            "type": "anomaly",
                            "source": f"pulse.{name}",
                            "error": steps[name].get("error", "unknown"),
                            "pulse_id": pid,
                        }
                    )
            self._emit(
                {
                    "type": "heartbeat",
                    "pulse_id": pid,
                    "count": entry["count"],
                    "timestamp": entry["timestamp"],
                    "elapsed_s": entry["elapsed_s"],
                    "interval_s": interval,
                    "interval_adapted_from": adapted_from,
                    "steps": steps,
                    "note": "step_* 为占位实现，返回值为常量",
                }
            )

    # ── L4 Evolve 观察 ──

    def _evolve_loop(self):
        from agent_core.meta_evolution import MetaEvolution

        try:
            evo = MetaEvolution()
        except Exception as e:
            self._emit({"type": "anomaly", "source": "evolve_init", "error": str(e)})
            return
        while not self._stop.wait(self.evolve_every_s):
            self._run_evolve_once(evo)

    def _run_evolve_once(self, evo):
        try:
            result = evo.run_full_cycle(task_history=[])
            phases = result.get("phases", {})
            report_path = result.get("report_path")
            snapshot = phases.get("self_versioning", {}).get("snapshot_path")
            reflector = phases.get("reflection", {}).get("reflector", {})
            artifacts = {
                "report_path": report_path,
                "report_exists": bool(report_path) and Path(report_path).exists(),
                "version_snapshot": snapshot,
                "version_snapshot_exists": bool(snapshot) and Path(snapshot).exists(),
                "skill_files_generated": "无（阶段3 仅计数，不落盘技能文件）",
                "memory_consolidation_files": "无（阶段4 返回固定 dict）",
            }
            self._emit(
                {
                    "type": "evolve_cycle",
                    "trigger": "script_manual（未观察到自动触发器：无任务后钩子、无每日02:00调度）",
                    "elapsed_ms": result.get("elapsed_ms"),
                    "version": phases.get("self_versioning", {}).get("version"),
                    "phases": {
                        "experience_replay": phases.get("experience_replay"),
                        "gap_analysis": phases.get("gap_analysis"),
                        "skill_gen": phases.get("skill_gen"),
                        "reflector": {
                            "accept": reflector.get("accept_count"),
                            "reject": reflector.get("reject_count"),
                            "llm_critique": reflector.get("llm_critique"),
                        },
                        "curator_gate": phases.get("reflection", {}).get("curator", {}).get("gate"),
                        "memory_consolidation": phases.get("memory_consolidation"),
                        "self_versioning": phases.get("self_versioning"),
                    },
                    "llm_disabled": os.environ.get("ECO_LLM_DISABLE", "").strip() in ("1", "true", "yes"),
                    "artifacts": artifacts,
                }
            )
        except Exception as e:
            self._emit({"type": "anomaly", "source": "evolve_cycle", "error": str(e)})

    def _watch_evolve_reports(self, known: set) -> set:
        """监视进化报告目录——捕获任何来源（含剧本外）生成的新报告文件"""
        if not EVOLVE_REPORT_DIR.exists():
            return known
        current = set(EVOLVE_REPORT_DIR.glob("evolution_report_v*.md"))
        for p in sorted(current - known):
            self._emit({"type": "evolve_report_detected", "path": str(p), "size_bytes": p.stat().st_size})
        return current

    # ── 主流程 ──

    def run(self) -> dict:
        from agent_core.heartbeat import PulseLoop

        pulse = PulseLoop()
        self._configure_pulse(pulse)
        self._register_steps(pulse)
        known_reports = set(EVOLVE_REPORT_DIR.glob("evolution_report_v*.md")) if EVOLVE_REPORT_DIR.exists() else set()

        started = time.time()
        self._jsonl_fh = open(self.jsonl_path, "w", encoding="utf-8")  # noqa: SIM115 长生命周期句柄，随 run 结束关闭
        reason = "deadline"
        try:
            self._emit(
                {
                    "type": "run_start",
                    "mode": "smoke" if self.smoke else "longrun",
                    "duration_s": self.duration_s,
                    "pulse_interval_s": pulse._interval,
                    "pulse_adaptive_bounds": [pulse._min_interval, pulse._max_interval],
                    "evolve_enabled": self.enable_evolve,
                    "evolve_every_s": self.evolve_every_s if self.enable_evolve else None,
                    "llm_disabled": os.environ.get("ECO_LLM_DISABLE", "").strip() in ("1", "true", "yes"),
                    "claim_vs_observed": [
                        {"claim": c, "verdict": v, "evidence": e, "mark": m} for c, v, e, m in CLAIM_VS_OBSERVED
                    ],
                }
            )
            pulse.start()
            if self.enable_evolve:
                threading.Thread(target=self._evolve_loop, daemon=True, name="evolve-trigger").start()
            while not self._stop.is_set() and time.time() - started < self.duration_s:
                self._collect_pulses(pulse)
                known_reports = self._watch_evolve_reports(known_reports)
                time.sleep(0.5)
            if self._sigint:
                reason = "sigint"
            elif self._stop.is_set():
                reason = "stopped"
        except KeyboardInterrupt:
            reason = "sigint"
        finally:
            pulse.stop()
            self._stop.set()
            self._emit(
                {
                    "type": "run_end",
                    "reason": reason,
                    "duration_s": round(time.time() - started, 1),
                    "pulse_stats": pulse.get_stats(),
                }
            )
            self._jsonl_fh.close()
            self._jsonl_fh = None
            self.generate_report(reason)
        return {"jsonl": str(self.jsonl_path), "report": str(self.md_path), "reason": reason}

    # ── 汇总报告 ──

    def generate_report(self, reason: str = "deadline") -> str:
        events = list(self._events)
        heartbeats = [e for e in events if e["type"] == "heartbeat"]
        evolves = [e for e in events if e["type"] == "evolve_cycle"]
        detected = [e for e in events if e["type"] == "evolve_report_detected"]
        anomalies = [e for e in events if e["type"] == "anomaly"]
        run_start = next((e for e in events if e["type"] == "run_start"), {})

        L = []
        L.append("# L3 Pulse 心跳 + L4 Evolve 进化 长时运行实证报告")
        L.append("")
        L.append(f"> 运行日期：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
        L.append(
            f"> 运行模式：{'smoke（压缩时序自检）' if self.smoke else 'longrun（长时观察）'}，计划时长 {self.duration_s:.0f}s"
        )
        L.append(f"> 结束原因：{reason}")
        L.append(f"> LLM：{'ECO_LLM_DISABLE=1（规则降级，LLM 章节跳过）' if run_start.get('llm_disabled') else '启用'}")
        L.append("")
        L.append("---")
        L.append("")

        # 一、L3 Pulse
        L.append("## 一、L3 Pulse 心跳观测")
        L.append("")
        L.append("### 1.1 心跳概览")
        L.append("")
        L.append("| 指标 | 值 |")
        L.append("|:-----|:---|")
        L.append(f"| 心跳总次数 | {len(heartbeats)} |")
        if heartbeats:
            L.append(f"| 首次心跳 | {heartbeats[0]['timestamp'][:19]} |")
            L.append(f"| 末次心跳 | {heartbeats[-1]['timestamp'][:19]} |")
            gaps = self._heartbeat_gaps(heartbeats)
            if gaps:
                L.append(f"| 实际间隔 min/avg/max | {min(gaps):.1f}s / {statistics.mean(gaps):.1f}s / {max(gaps):.1f}s |")
                if len(gaps) >= 2:
                    L.append(f"| 间隔中位数 | {statistics.median(gaps):.1f}s |")
            L.append(
                f"| 配置间隔 / 自适应边界 | {run_start.get('pulse_interval_s')}s / {run_start.get('pulse_adaptive_bounds')} |"
            )
        else:
            L.append("| ⚠️ 未观察到任何心跳 | 运行时长可能不足一个心跳周期 |")
        L.append("")

        L.append("### 1.2 自适应降频行为")
        L.append("")
        adapted = [h for h in heartbeats if h.get("interval_adapted_from") is not None]
        if adapted:
            L.append("| 心跳 | 间隔调整 | 调整后 |")
            L.append("|:-----|:---------|:-------|")
            for h in adapted:
                L.append(
                    f"| {h['pulse_id']} | {h['interval_adapted_from']:g}s → {h['interval_s']:g}s | 本次心跳耗时 {h['elapsed_s']}s |"  # noqa: E501
                )
        else:
            L.append("未观察到间隔自适应调整（各次心跳耗时均低于触发阈值，或观察时长不足）。")
        L.append("")

        L.append("### 1.3 五个内置步骤执行痕迹")
        L.append("")
        L.append("| 步骤 | 声称职责 | 观察到的返回值 | 性质 |")
        L.append("|:-----|:---------|:---------------|:-----|")
        for name in self.PULSE_STEPS:
            vals = sorted(
                {str(h["steps"].get(name, {}).get("result", h["steps"].get(name, {}).get("status", "N/A"))) for h in heartbeats}
            ) or ["未执行"]
            L.append(f"| {name} | {STEP_DUTIES[name]} | {', '.join(vals)} | 占位实现（常量返回） |")
        L.append("")
        L.append(
            "> 注：生产接线 `EcoLoops.start()` 仅注册 sync/diff 两个 listener，rule_engine/mem_cron/suggestions 在真实运行中不会执行；本剧本为观察目的注册了全部 5 个。"  # noqa: E501
        )
        L.append("")

        # 二、L4 Evolve
        L.append("## 二、L4 Evolve 进化观测")
        L.append("")
        L.append("### 2.1 进化触发")
        L.append("")
        L.append(f"- 剧本内进化循环次数：**{len(evolves)}**")
        L.append(
            "- 触发方式：`script_manual`——**未观察到自动触发器**（无任务完成钩子、无每日 02:00 调度接线），与 README「每次任务后 / 每日」的声称不符"  # noqa: E501
        )
        L.append("")
        if evolves:
            L.append("### 2.2 五阶段产物清单")
            L.append("")
            L.append("| 轮次 | 版本 | 耗时 | 回放/差距 | 技能生成 | 反思门禁 | 版本快照 | 报告文件 |")
            L.append("|:-----|:-----|:-----|:----------|:---------|:---------|:---------|:---------|")
            for i, e in enumerate(evolves, 1):
                p = e["phases"]
                replay = p.get("experience_replay") or {}
                gap = p.get("gap_analysis") or {}
                sg = p.get("skill_gen") or {}
                art = e["artifacts"]
                L.append(
                    f"| #{i} | v{e.get('version')} | {e.get('elapsed_ms')}ms "
                    f"| 回放{replay.get('total_replayed')}/差距{gap.get('gap_count')} "
                    f"| 增{sg.get('generated')}/优{sg.get('optimized')}（无落盘文件） "
                    f"| {p.get('curator_gate')} "
                    f"| {'✅' if art['version_snapshot_exists'] else '❌'} "
                    f"| {'✅' if art['report_exists'] else '❌'} |"
                )
            L.append("")
            L.append(f"- 阶段3 技能生成：{evolves[-1]['artifacts']['skill_files_generated']}")
            L.append(f"- 阶段4 记忆固化：{evolves[-1]['artifacts']['memory_consolidation_files']}")
            if run_start.get("llm_disabled"):
                L.append("- LLM 环节（Reflector 对抗质询、元认知分析章节）：ECO_LLM_DISABLE=1 下规则降级/跳过")
            L.append("")
        if detected:
            L.append("### 2.3 观察期间生成的进化报告文件")
            L.append("")
            for d in detected:
                L.append(f"- `{d['path']}`（{d['size_bytes']}B）")
            L.append("")

        # 三、声称 vs 实测
        L.append("## 三、README 声称 vs 实测对照")
        L.append("")
        L.append("| README 声称 | 实测结论 | 证据 | 状态 |")
        L.append("|:-------------|:---------|:-----|:----:|")
        for claim, verdict, evidence, mark in CLAIM_VS_OBSERVED:
            L.append(f"| {claim} | {verdict} | {evidence} | {mark} |")
        L.append("")

        # 四、异常
        L.append("## 四、异常清单")
        L.append("")
        if anomalies:
            L.append("| 时间 | 来源 | 错误 |")
            L.append("|:-----|:-----|:-----|")
            for a in anomalies:
                L.append(f"| {a['ts'][:19]} | {a['source']} | {a['error']} |")
        else:
            L.append("无异常。✅")
        L.append("")

        # 五、产物
        L.append("## 五、产物清单")
        L.append("")
        L.append(f"- 事件流（JSONL）：`{self.jsonl_path}`（{len(events)} 条事件）")
        L.append(f"- 本报告：`{self.md_path}`")
        L.append("")

        self.md_path.write_text("\n".join(L), encoding="utf-8")
        return str(self.md_path)

    @staticmethod
    def _heartbeat_gaps(heartbeats: list[dict]) -> list[float]:
        gaps = []
        for prev, cur in zip(heartbeats, heartbeats[1:], strict=False):
            try:
                t0 = datetime.fromisoformat(prev["timestamp"])
                t1 = datetime.fromisoformat(cur["timestamp"])
                gaps.append((t1 - t0).total_seconds())
            except (KeyError, ValueError):
                continue
        return gaps


def main():
    ap = argparse.ArgumentParser(description="L3 Pulse + L4 Evolve 长时运行实证剧本")
    ap.add_argument("--hours", type=float, default=24.0, help="观察时长（小时），默认 24")
    ap.add_argument("--seconds", type=float, default=None, help="观察时长（秒），优先级高于 --hours")
    ap.add_argument("--smoke", action="store_true", help="压缩时序自检：心跳秒级、默认跑 120s")
    ap.add_argument("--pulse-interval", type=float, default=None, help="覆盖心跳起始间隔（秒）")
    ap.add_argument("--evolve-every", type=float, default=None, help="脚本手动触发进化间隔（秒，L4 无自动触发器）")
    ap.add_argument("--no-evolve", action="store_true", help="只观察 L3，不触发 L4 进化")
    ap.add_argument("--reports-dir", type=Path, default=REPORTS_DIR, help="报告输出目录")
    args = ap.parse_args()

    duration = args.seconds if args.seconds is not None else (120.0 if args.smoke else args.hours * 3600)
    obs = LongRunObserver(
        duration_s=duration,
        smoke=args.smoke,
        reports_dir=args.reports_dir,
        pulse_interval_s=args.pulse_interval,
        evolve_every_s=args.evolve_every,
        enable_evolve=not args.no_evolve,
    )
    obs.install_sigint_handler()
    print(
        f"[LongRun] 模式={'smoke' if args.smoke else 'longrun'} 时长={duration:.0f}s "
        f"进化={'每' + str(obs.evolve_every_s) + 's手动触发' if obs.enable_evolve else '关闭'}"
    )
    print(f"[LongRun] JSONL → {obs.jsonl_path}")
    out = obs.run()
    print(f"[LongRun] 结束（{out['reason']}）→ 报告 {out['report']}")


if __name__ == "__main__":
    main()
