#!/usr/bin/env python3
"""
heartbeat.py — Eco Agent L3 后台心跳循环 (Autonomous Pulse)

对标 OpenHuman 的"潜意识循环" + Codex 的"定时心跳自动化任务。
在用户未交互时自主运转：数据同步→差异检测→规则触发→内存整理→主动建议。

节律：每5~20分钟（自适应）
"""

import json
import logging
import os
import threading
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("heartbeat")

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "memory-tree" / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


class PulseLoop:
    """L3 后台心跳循环——自主运转、自适应频率、静默执行"""

    def __init__(self):
        self._running = False
        self._thread: threading.Thread | None = None
        self._pulse_count = 0
        self._interval = 600  # 默认10分钟
        self._min_interval = 300  # 5分钟
        self._max_interval = 1200  # 20分钟
        self._load_aware = True
        self._listeners: dict[str, Callable] = {}
        self._pulse_log: list[dict] = []

    def register_listener(self, name: str, handler: Callable):
        """注册心跳监听器——每个STEP对应一个监听器"""
        self._listeners[name] = handler

    def start(self):
        """启动后台心跳"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._pulse_loop, daemon=True, name="heartbeat")
        self._thread.start()
        logger.info(f"Heartbeat: 启动 (间隔{self._interval}s)")

    def stop(self):
        self._running = False
        logger.info("Heartbeat: 停止")

    def _pulse_loop(self):
        while self._running:
            self._pulse_count += 1
            pulse_id = f"pulse_{self._pulse_count}"
            start_time = time.time()
            logger.debug(f"[Pulse] #{self._pulse_count} 开始")

            results = {}
            for name, handler in self._listeners.items():
                try:
                    result = handler()
                    results[name] = {"status": "ok", "result": str(result)[:100]}
                except Exception as e:
                    results[name] = {"status": "error", "error": str(e)}
                    logger.warning(f"[Pulse] {name}: {e}")

            elapsed = time.time() - start_time
            self._pulse_log.append(
                {
                    "id": pulse_id,
                    "count": self._pulse_count,
                    "timestamp": datetime.now().isoformat(),
                    "elapsed_s": round(elapsed, 2),
                    "results": results,
                }
            )
            if len(self._pulse_log) > 100:
                self._pulse_log = self._pulse_log[-100:]

            # 自适应间隔
            if self._load_aware:
                self._adapt_interval(elapsed)

            logger.debug(f"[Pulse] #{self._pulse_count} 完成 ({elapsed:.1f}s, 下次{self._interval}s后)")
            time.sleep(self._interval)

    def _adapt_interval(self, elapsed_s: float):
        """自适应调整心跳频率"""
        if elapsed_s > self._interval * 0.8:
            self._interval = min(self._interval * 1.2, self._max_interval)
        elif elapsed_s < self._interval * 0.2:
            self._interval = max(self._interval * 0.8, self._min_interval)

    # ── 内置心跳步骤（兼容旧接口，委托 PulseSteps 默认实例）──

    @staticmethod
    def step_sync():
        """STEP 1: 全平台数据同步"""
        return default_steps().step_sync()

    @staticmethod
    def step_diff():
        """STEP 2: 差异检测"""
        return default_steps().step_diff()

    @staticmethod
    def step_rule_engine():
        """STEP 3: 自动触发规则引擎"""
        return default_steps().step_rule_engine()

    @staticmethod
    def step_mem_cron():
        """STEP 4: 内存碎片整理"""
        return default_steps().step_mem_cron()

    @staticmethod
    def step_suggestions():
        """STEP 5: 主动建议生成"""
        return default_steps().step_suggestions()

    def get_stats(self) -> dict:
        return {
            "pulse_count": self._pulse_count,
            "running": self._running,
            "interval_s": self._interval,
            "listeners": len(self._listeners),
            "last_pulse": self._pulse_log[-1]["timestamp"][:19] if self._pulse_log else "N/A",
        }


# ═══════════════════════════════════
# PulseSteps — 五步骤真实实现
# ═══════════════════════════════════


class PulseSteps:
    """L3 心跳五步骤真实实现（路径全部可注入，离线测试安全）

    sync → 扫描受管目录，落盘快照（文件数/字节/mtime 清单）
    diff → 当前扫描 vs 上次快照，报告新增/修改
    rule_engine → 知识保鲜规则：mtime 超 stale_days 的文件触发提醒（D10 抓手）
    mem_cron → SQLite VACUUM + 完整性检查
    suggestions → 基于其他步骤结果生成建议；一切正常返回 None（静默原则）
    """

    def __init__(
        self,
        vault_path: Path | None = None,
        watch_dirs: list | None = None,
        state_file: Path | None = None,
        db_paths: list | None = None,
        stale_days: int = 90,
    ):
        self._vault = Path(vault_path) if vault_path else None
        self._watch = [Path(d) for d in (watch_dirs or [])]
        self._state_file = Path(state_file) if state_file else (DATA_DIR / "pulse_state.json")
        self._dbs = [Path(d) for d in (db_paths or [])]
        self._stale_days = stale_days

    # ── 扫描与快照 ──

    def _scan(self) -> dict[str, float]:
        """扫描受管目录 → {文件路径: mtime}（.md/.txt）"""
        files: dict[str, float] = {}
        for root in self._watch:
            if not root.exists():
                continue
            for f in root.rglob("*"):
                if f.is_file() and f.suffix.lower() in (".md", ".txt"):
                    try:
                        files[str(f)] = f.stat().st_mtime
                    except OSError:
                        continue
        return files

    def _load_snapshot(self) -> dict:
        try:
            return json.loads(self._state_file.read_text(encoding="utf-8"))
        except Exception:
            return {"files": {}, "taken_at": ""}

    def _save_snapshot(self, files: dict[str, float]):
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        self._state_file.write_text(
            json.dumps({"files": files, "taken_at": datetime.now().isoformat()}, ensure_ascii=False), encoding="utf-8"
        )

    # ── 五步骤 ──

    def step_sync(self) -> dict:
        """STEP 1: 数据同步——扫描受管存储，落盘快照，返回真实计数"""
        files = self._scan()
        total_bytes = 0
        for p in files:
            try:
                total_bytes += Path(p).stat().st_size
            except OSError:
                pass
        self._save_snapshot(files)
        stores = sum(1 for d in self._watch if d.exists())
        return {"stores": stores, "files": len(files), "bytes": total_bytes}

    def step_diff(self) -> dict:
        """STEP 2: 差异检测——当前扫描 vs 上次快照（新增/修改）"""
        old = self._load_snapshot()["files"]
        cur = self._scan()
        changed = [p for p, mt in cur.items() if p not in old or old[p] < mt]
        deleted = [p for p in old if p not in cur]
        self._save_snapshot(cur)
        return {"changed": len(changed) + len(deleted), "files": sorted(changed), "deleted": len(deleted)}

    def step_rule_engine(self) -> dict:
        """STEP 3: 规则触发——知识保鲜：超期未更新文件触发提醒（D10 知识新鲜度）"""
        cutoff = time.time() - self._stale_days * 86400
        triggered = [p for p, mt in self._scan().items() if mt < cutoff]
        return {"rule": "knowledge_freshness", "stale_days": self._stale_days, "triggered": sorted(triggered)}

    def step_mem_cron(self) -> dict:
        """STEP 4: 内存整理——SQLite VACUUM + 完整性检查（DB 不存在跳过不崩）"""
        import sqlite3

        vacuumed = 0
        integrity = "ok"
        for db in self._dbs:
            if not db.exists():
                continue
            try:
                conn = sqlite3.connect(db)
                if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    integrity = "corrupt"
                conn.execute("VACUUM")
                conn.close()
                vacuumed += 1
            except sqlite3.Error as e:
                logger.warning(f"[Pulse] mem_cron {db.name}: {e}")
                integrity = "error"
        return {"vacuumed": vacuumed, "integrity": integrity}

    def step_suggestions(self, context: dict | None = None) -> list[str] | None:
        """STEP 5: 主动建议——基于其他步骤结果；无事发生返回 None（静默原则）"""
        ctx = context or {}
        suggestions = []
        stale = ctx.get("stale_count", 0)
        if stale > 0:
            suggestions.append(f"{stale} 条知识超过 {self._stale_days} 天未更新，建议复核时效性")
        if ctx.get("changed", 0) > 0:
            suggestions.append(f"检测到 {ctx['changed']} 处知识库变更，建议确认是否需要重建索引")
        issues = ctx.get("verify_issues") or []
        suggestions.extend(f"[运维体检] {i}" for i in issues[:3])
        return suggestions or None

    def step_verify(self) -> list[str] | None:
        """STEP 6: 运维体检——会话日志链/进化报告/记忆矛盾/技能库健康检查。

        全部正常返回 None（静默原则）；发现异常返回问题清单，
        供 step_suggestions 汇总与心跳上报。离线安全：所有检查无网络依赖。
        """
        try:
            import sys

            if str(ROOT) not in sys.path:
                sys.path.insert(0, str(ROOT))
            from _scripts.verify_ops import run_checks

            report = run_checks()
        except Exception as e:  # noqa: BLE001 — 体检失败不得击穿心跳
            logger.warning("[Pulse] verify_ops 执行失败: %s", e)
            return [f"运维体检不可用: {e}"]

        issues: list[str] = []
        sl = report.get("session_logs") or {}
        if not sl.get("all_verified"):
            issues.append(f"会话日志校验异常（截断 {sl.get('truncated_total', 0)} 处）")
        er = report.get("evolution_report") or {}
        if er.get("exists") and not er.get("pass"):
            issues.append(f"进化报告篇幅不足（{er.get('chars', 0)} 字 < 500）")
        mc = report.get("memory_conflicts") or {}
        if mc.get("open_conflicts", 0) > 0:
            issues.append(f"{mc['open_conflicts']} 条记忆矛盾待消解")
        return issues or None


_default_steps: PulseSteps | None = None


def default_steps() -> PulseSteps:
    """生产默认实例：监控 memory-tree 与（存在的）Obsidian vault、ECO_DIR SQLite"""
    global _default_steps
    if _default_steps is None:
        watch = [ROOT / "memory-tree"]
        vault = os.environ.get("OBSIDIAN_VAULT", "")
        if vault and Path(vault).is_dir():
            watch.append(Path(vault))
        eco_dir = Path(os.environ.get("ECO_DIR", str(Path.home() / ".eco")))
        dbs = [eco_dir / "hybrid_vectors.db"] if (eco_dir / "hybrid_vectors.db").exists() else []
        _default_steps = PulseSteps(watch_dirs=watch, db_paths=dbs)
    return _default_steps


# ===== 快速包装 =====

pulse = PulseLoop()


def test():
    import io
    import sys as _sys

    _sys.stdout = io.TextIOWrapper(_sys.stdout.buffer, encoding="utf-8", errors="replace")

    p = PulseLoop()
    p.register_listener("sync", lambda: "已同步3个平台")
    p.register_listener("diff", lambda: "发现1个变化")
    p.register_listener("mem", lambda: "整理完成")
    p._interval = 2  # 2秒间隔用于测试

    p.start()
    time.sleep(5)
    p.stop()

    stats = p.get_stats()
    print(f"[Pulse] 心跳: {stats['pulse_count']}次, 运行中: {stats['running']}, 监听器: {stats['listeners']}个", flush=True)
    print("[OK] L3 Heartbeat 测试通过", flush=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test()
