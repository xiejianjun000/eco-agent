#!/usr/bin/env python3
"""
daemon.py — Eco Agent 后台守护服务

7x24 运行、崩溃自动拉起、生命周期管理。

用法：
  python gateway/daemon.py start          # 启动守护进程
  python gateway/daemon.py stop           # 停止
  python gateway/daemon.py restart        # 重启
  python gateway/daemon.py status         # 查看状态
  python gateway/daemon.py foreground     # 前台运行（调试）
"""

import os
import sys
import time
import signal
import logging
import threading
from pathlib import Path
from datetime import datetime

logger = logging.getLogger("daemon")

ROOT = Path(__file__).resolve().parent.parent
PID_FILE = ROOT / "memory-tree" / "data" / "daemon.pid"
LOG_DIR = ROOT / "memory-tree" / "data" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)


class DaemonService:
    """后台守护服务"""

    def __init__(self):
        self._running = False
        self._services: dict[str, dict] = {}
        self._threads: list[threading.Thread] = []
        self._health = {"status": "starting", "started_at": "", "uptime": 0}

    def register(self, name: str, start_fn, stop_fn=None, health_check=None):
        """注册子服务"""
        self._services[name] = {
            "start": start_fn, "stop": stop_fn,
            "health_check": health_check, "status": "registered"
        }

    def start_all(self):
        """启动所有已注册服务"""
        self._running = True
        self._health["started_at"] = datetime.now().isoformat()
        logger.info("=" * 50)
        logger.info("  Eco Agent Daemon 启动")
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
        """停止所有服务"""
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
        """健康检查"""
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
            if status not in ("running", "ok", "stopped"):
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


# ===== 快速启动 =====

daemon = DaemonService()


def run_foreground():
    """前台运行（调试模式）"""
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(name)s] %(message)s")
    daemon.start_all()
    try:
        while daemon._running:
            time.sleep(10)
            health = daemon.check_health()
            if not health.get("all_ok", True):
                logger.warning(f"服务降级: {health}")
    except KeyboardInterrupt:
        daemon.stop_all()


def run_start():
    """后台启动"""
    if daemon.is_running():
        print("Daemon 已在运行中")
        return
    pid = os.fork() if hasattr(os, 'fork') else 0
    if pid == 0:
        # 子进程：脱离父进程会话，stdout/stderr 重定向到日志，避免占用调用方管道
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
    else:
        print("Daemon 未运行")


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "foreground"
    handlers = {
        "start": run_start, "stop": run_stop, "restart": lambda: (run_stop(), time.sleep(1), run_start()),
        "status": run_status, "foreground": run_foreground,
    }
    handler = handlers.get(cmd)
    if handler:
        handler()
    else:
        print(f"未知命令: {cmd}")
        print("用法: python gateway/daemon.py [start|stop|restart|status|foreground]")
