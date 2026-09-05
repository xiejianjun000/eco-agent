#!/usr/bin/env python3
"""
daemon.py — Eco Agent 后台守护服务（补强版）

新增：
- CronScheduler 集成：注册 L4 每日进化、L3 Pulse 静默任务
- WeChat 个人号通道自动注册
- 全量 PulseSteps 接线（L3 五步骤完整启用）
- 任务完成钩子桥接（Commander → L4 自动进化）
- 健康检查面板升级
"""

import logging
import os
import signal
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("daemon")

ROOT = Path(__file__).resolve().parent.parent
PID_FILE = ROOT / "memory-tree" / "data" / "daemon.pid"
LOG_DIR = ROOT / "memory-tree" / "data" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)


class DaemonService:
    """后台守护服务（补强版）"""

    def __init__(self):
        self._running = False
        self._services: dict[str, dict] = {}
        self._threads: list[threading.Thread] = []
        self._health = {"status": "starting", "started_at": "", "uptime": 0}
        self._eco_loops = None  # 延迟导入

    def register(self, name: str, start_fn, stop_fn=None, health_check=None):
        self._services[name] = {
            "start": start_fn,
            "stop": stop_fn,
            "health_check": health_check,
            "status": "registered",
        }

    def init_all_services(self):
        """初始化并注册所有子服务"""

        # ── 服务 1: 五层循环（L1/L3/L4/L5） ──
        def _start_loops():
            from agent_core.eco_loops_integration import loops

            self._eco_loops = loops
            loops.start()
            logger.info("[Daemon] 五层循环已启动 (L1+L3+L4+L5)")

        def _stop_loops():
            if self._eco_loops:
                self._eco_loops.stop()

        def _health_loops():
            if self._eco_loops:
                s = self._eco_loops.get_stats()
                return {"ok": self._eco_loops.l3._running, **s}
            return {"ok": False}

        self.register("eco_loops", _start_loops, _stop_loops, _health_loops)

        # ── 服务 2: Cron 调度器（新增！） ──
        def _start_scheduler():
            try:
                from agent_core.scheduler import scheduler

                scheduler.start()
                logger.info(f"[Daemon] Cron 调度器已启动 ({len(scheduler._jobs)} 个任务)")
            except ImportError as e:
                logger.info(f"[Daemon] Cron 调度器未加载: {e}")

        def _stop_scheduler():
            try:
                from agent_core.scheduler import scheduler

                scheduler.stop()
            except ImportError:
                pass

        def _health_scheduler():
            try:
                from agent_core.scheduler import scheduler

                s = scheduler.get_stats()
                return {"ok": s["running"], **s}
            except ImportError:
                return {"ok": False, "error": "模块未加载"}

        self.register("cron_scheduler", _start_scheduler, _stop_scheduler, _health_scheduler)

        # ── 服务 3: 微信个人号通道（新增！） ──
        def _start_wechat():
            try:
                from agent_core.channels.wechat_personal import wechat_bot

                # 有消息回调时走 Agent 引擎
                wechat_bot.start()
                logger.info("[Daemon] 微信个人号通道尝试启动（等待扫码）")
            except ImportError as e:
                logger.info(f"[Daemon] 微信通道未加载: {e}")

        def _stop_wechat():
            try:
                from agent_core.channels.wechat_personal import wechat_bot

                wechat_bot.stop()
            except ImportError:
                pass

        def _health_wechat():
            try:
                from agent_core.channels.wechat_personal import wechat_bot

                return wechat_bot.get_health()
            except ImportError:
                return {"ok": False, "status": "not_loaded"}

        wechat_enabled = os.environ.get("ECO_WECHAT_ENABLED", "false").lower() == "true"
        if wechat_enabled:
            self.register("wechat_personal", _start_wechat, _stop_wechat, _health_wechat)

        # ── 服务 4: 统一网关（Telegram/Discord/Slack） ──
        def _start_gateway():
            try:
                from gateway.channels.telegram import start_telegram

                start_telegram()
                logger.info("[Daemon] Telegram 通道已启动")
            except ImportError:
                logger.debug("[Daemon] Telegram 通道未加载")
            try:
                from gateway.channels.discord import start_discord

                start_discord()
                logger.info("[Daemon] Discord 通道已启动")
            except ImportError:
                logger.debug("[Daemon] Discord 通道未加载")

        def _stop_gateway():
            pass

        self.register("gateway", _start_gateway, _stop_gateway)

        # ── 服务 5: 国内平台网关（飞书/企微/钉钉） ──
        def _start_domestic():
            try:
                from agent_core.channels.feishu import start_feishu

                start_feishu()
                logger.info("[Daemon] 飞书通道已启动")
            except ImportError:
                logger.debug("[Daemon] 飞书通道未加载")
            try:
                from agent_core.channels.wecom import start_wecom

                start_wecom()
                logger.info("[Daemon] 企微通道已启动")
            except ImportError:
                logger.debug("[Daemon] 企微通道未加载")
            try:
                from agent_core.channels.dingtalk import start_dingtalk

                start_dingtalk()
                logger.info("[Daemon] 钉钉通道已启动")
            except ImportError:
                logger.debug("[Daemon] 钉钉通道未加载")

        def _stop_domestic():
            pass

        self.register("domestic_gateway", _start_domestic, _stop_domestic)

    def start_all(self):
        """启动所有已注册服务"""
        self.init_all_services()
        self._running = True
        self._health["started_at"] = datetime.now().isoformat()

        logger.info("=" * 50)
        logger.info("  Eco Agent Daemon 启动（补强版）")
        logger.info(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"  注册服务: {len(self._services)} 个")
        logger.info("=" * 50)

        for name, svc in self._services.items():
            try:
                svc["start"]()
                svc["status"] = "running"
                logger.info(f"  [OK] {name}")
            except Exception as e:
                svc["status"] = f"failed: {e}"
                logger.warning(f"  [FAIL] {name}: {e}")

        self._health["status"] = "running"
        self._write_pid()

    def stop_all(self):
        logger.info("Daemon 正在关闭...")
        self._running = False
        for name, svc in reversed(list(self._services.items())):
            if svc.get("stop"):
                try:
                    svc["stop"]()
                    svc["status"] = "stopped"
                except Exception as e:
                    logger.warning(f"停止 {name} 失败: {e}")
        self._cleanup_pid()
        logger.info("Daemon 已关闭")

    def check_health(self) -> dict:
        self._health["uptime"] = self._calc_uptime()
        services = {}
        all_ok = True
        for name, svc in self._services.items():
            status = svc["status"]
            if svc.get("health_check"):
                try:
                    h = svc["health_check"]()
                    if not h.get("ok", True):
                        all_ok = False
                    status = "ok" if h.get("ok", True) else "degraded"
                except Exception:
                    status = "error"
                    all_ok = False
            services[name] = status
            if status not in ("running", "ok", "stopped", "registered"):
                all_ok = False
        self._health["services"] = services
        self._health["all_ok"] = all_ok
        return self._health

    def _calc_uptime(self) -> str:
        if not self._health["started_at"]:
            return "0s"
        try:
            start = datetime.fromisoformat(self._health["started_at"])
            delta = datetime.now() - start
            total = int(delta.total_seconds())
            h, m = divmod(total, 3600)
            m, s = divmod(m, 60)
            return f"{h}h{m}m{s}s"
        except Exception:
            return "?"

    def _write_pid(self):
        PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        PID_FILE.write_text(str(os.getpid()))

    def _cleanup_pid(self):
        if PID_FILE.exists():
            PID_FILE.unlink()

    @classmethod
    def is_running(cls) -> bool:
        if not PID_FILE.exists():
            return False
        try:
            pid = int(PID_FILE.read_text().strip())
            os.kill(pid, 0)
            return True
        except Exception:
            return False


daemon = DaemonService()


def run_foreground():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
    daemon.start_all()
    try:
        while daemon._running:
            time.sleep(10)
            health = daemon.check_health()
            if not health.get("all_ok", True):
                degraded = [f"{k}={v}" for k, v in health.get("services", {}).items() if v not in ("running", "ok", "stopped")]
                logger.warning(f"服务降级: {degraded}")
    except KeyboardInterrupt:
        daemon.stop_all()


def run_start():
    if daemon.is_running():
        print("Daemon 已在运行中")
        return
    pid = os.fork() if hasattr(os, "fork") else 0
    if pid == 0:
        try:
            os.setsid()
        except OSError:
            pass
        sys.stdin.close()
        log_path = LOG_DIR / "daemon.out.log"
        fd = os.open(str(log_path), os.O_WRONLY | os.O_CREAT | os.O_APPEND)
        os.dup2(fd, sys.stdout.fileno())
        os.dup2(fd, sys.stderr.fileno())
        os.close(fd)
        run_foreground()
    else:
        print(f"Daemon 已启动 (PID: {pid})")


def run_stop():
    pid_path = PID_FILE
    if pid_path.exists():
        pid = int(pid_path.read_text().strip())
        try:
            os.kill(pid, signal.SIGTERM)
            print(f"Daemon (PID: {pid}) 已停止")
        except ProcessLookupError:
            print("Daemon 未运行")
        pid_path.unlink(missing_ok=True)
    else:
        print("Daemon 未运行")


def run_status():
    if daemon.is_running():
        pid = PID_FILE.read_text().strip()
        print(f"Daemon 运行中 (PID: {pid})")
        # 尝试读取健康状态
        try:
            health = daemon.check_health()
            print(f"  服务数: {len(health.get('services', {}))}")
            for svc, status in health.get("services", {}).items():
                icon = "OK" if status in ("running", "ok", "stopped") else "!!"
                print(f"  [{icon}] {svc}: {status}")
        except Exception:
            pass
    else:
        print("Daemon 未运行")


if __name__ == "__main__":
    import sys

    cmd = sys.argv[1] if len(sys.argv) > 1 else "foreground"
    handlers = {
        "start": run_start,
        "stop": run_stop,
        "restart": lambda: (run_stop(), time.sleep(1), run_start()),
        "status": run_status,
        "foreground": run_foreground,
    }
    handler = handlers.get(cmd)
    if handler:
        handler()
    else:
        print(f"未知命令: {cmd}")
        print("用法: python gateway/daemon.py [start|stop|restart|status|foreground]")
