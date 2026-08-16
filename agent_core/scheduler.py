#!/usr/bin/env python3
"""
scheduler.py — Eco Agent 内置 Cron 定时任务调度器

对标 OpenClaw/Hermes 的内置定时任务能力，支持自然语言描述定时任务。
L4 Evolve 每日自动触发、主动建议推送等后台任务统一由此调度。

用法：
  eco cron add "每天 17:00 整理日志"      # 自然语言添加
  eco cron add --cron "0 2 * * *" --task "每日进化"  # cron 表达式
  eco cron list                            # 列出所有任务
  eco cron remove <job_id>                 # 移除任务
  eco cron run <job_id>                    # 手动触发
"""

import json
import time
import logging
import threading
from pathlib import Path
from datetime import datetime
from croniter import croniter

logger = logging.getLogger("scheduler")

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "memory-tree" / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
JOBS_FILE = DATA_DIR / "scheduled_jobs.json"

# 自然语言 → cron 表达式映射（常见模式）
NL_TO_CRON = {
    "每天凌晨": "0 0 * * *",
    "每天午夜": "0 0 * * *",
    "每天早晨": "0 8 * * *",
    "每天上午": "0 9 * * *",
    "每天中午": "0 12 * * *",
    "每天下午": "0 14 * * *",
    "每天傍晚": "0 18 * * *",
    "每天晚上": "0 20 * * *",
    "每小时": "0 * * * *",
    "每30分钟": "*/30 * * * *",
    "每周一": "0 9 * * 1",
    "每周五": "0 17 * * 5",
}

# 带时间的自然语言映射
NL_TIME_PATTERNS = {
    "每天 2:00": "0 2 * * *",
    "每天 3:00": "0 3 * * *",
    "每天 8:00": "0 8 * * *",
    "每天 9:00": "0 9 * * *",
    "每天 12:00": "0 12 * * *",
    "每天 17:00": "0 17 * * *",
    "每天 18:00": "0 18 * * *",
    "每天 20:00": "0 20 * * *",
    "每天 22:00": "0 22 * * *",
}


def nl_to_cron(description: str) -> str | None:
    """自然语言描述转 cron 表达式"""
    desc_lower = description.lower().strip()
    # 精确匹配带时间的模式
    for pattern, cron in sorted(NL_TIME_PATTERNS.items(), key=lambda x: -len(x[0])):
        if pattern in desc_lower:
            return cron
    # 模糊匹配
    for pattern, cron in NL_TO_CRON.items():
        if pattern in desc_lower:
            return cron
    return None


class ScheduledJob:
    """单个定时任务"""

    def __init__(self, job_id: str, cron_expr: str, task_desc: str,
                 handler_name: str = "", enabled: bool = True):
        self.job_id = job_id
        self.cron_expr = cron_expr
        self.task_desc = task_desc
        self.handler_name = handler_name
        self.enabled = enabled
        self.last_run: str | None = None
        self.next_run: str | None = None
        self.run_count: int = 0
        self.fail_count: int = 0
        self._iter = croniter(cron_expr, datetime.now())

    def should_run(self) -> bool:
        if not self.enabled:
            return False
        now = datetime.now()
        next_time = self._iter.get_next(datetime)
        self.next_run = next_time.isoformat()
        if now >= next_time:
            self._iter = croniter(self.cron_expr, now)
            return True
        return False

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id, "cron_expr": self.cron_expr,
            "task_desc": self.task_desc, "handler_name": self.handler_name,
            "enabled": self.enabled, "last_run": self.last_run,
            "next_run": self.next_run, "run_count": self.run_count,
            "fail_count": self.fail_count,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ScheduledJob":
        job = cls(d["job_id"], d["cron_expr"], d["task_desc"],
                  d.get("handler_name", ""), d.get("enabled", True))
        job.last_run = d.get("last_run")
        job.next_run = d.get("next_run")
        job.run_count = d.get("run_count", 0)
        job.fail_count = d.get("fail_count", 0)
        return job


class CronScheduler:
    """内置 Cron 调度器——对标 OpenClaw/Hermes"""

    def __init__(self, jobs_file: str | Path | None = None):
        self._running = False
        self._thread: threading.Thread | None = None
        self._jobs: dict[str, ScheduledJob] = {}
        self._handlers: dict[str, callable] = {}
        self._check_interval = 30  # 30秒检查一次
        # 可注入任务持久化路径：生产用默认 JOBS_FILE，测试可传临时路径实现隔离
        self._jobs_file = Path(jobs_file) if jobs_file else JOBS_FILE
        self._load_jobs()

    def register_handler(self, name: str, handler: callable):
        """注册任务处理器"""
        self._handlers[name] = handler

    def add_job(self, cron_expr: str, task_desc: str,
                handler_name: str = "") -> str:
        """添加定时任务，返回 job_id"""
        import uuid
        job_id = f"job_{uuid.uuid4().hex[:8]}"
        job = ScheduledJob(job_id, cron_expr, task_desc, handler_name)
        self._jobs[job_id] = job
        self._save_jobs()
        logger.info(f"[Scheduler] 添加任务: {job_id} -> {cron_expr} ({task_desc})")
        return job_id

    def add_from_nl(self, description: str, handler_name: str = "") -> str | None:
        """从自然语言描述添加定时任务"""
        cron_expr = nl_to_cron(description)
        if not cron_expr:
            logger.warning(f"[Scheduler] 无法解析自然语言: {description}")
            return None
        return self.add_job(cron_expr, description, handler_name)

    def remove_job(self, job_id: str) -> bool:
        if job_id in self._jobs:
            del self._jobs[job_id]
            self._save_jobs()
            return True
        return False

    def list_jobs(self) -> list[dict]:
        return [j.to_dict() for j in self._jobs.values()]

    def run_job(self, job_id: str) -> dict:
        """手动触发执行"""
        if job_id not in self._jobs:
            return {"error": f"任务 {job_id} 不存在"}
        job = self._jobs[job_id]
        return self._execute_job(job)

    def _execute_job(self, job: ScheduledJob) -> dict:
        """执行单个任务"""
        result = {"job_id": job.job_id, "task": job.task_desc, "success": False}
        try:
            handler = self._handlers.get(job.handler_name)
            if handler:
                handler_output = handler()
                result["output"] = str(handler_output)[:500]
            else:
                result["output"] = f"已触发: {job.task_desc}"
            result["success"] = True
            job.run_count += 1
        except Exception as e:
            result["error"] = str(e)
            job.fail_count += 1
            logger.warning(f"[Scheduler] 任务 {job.job_id} 失败: {e}")
        job.last_run = datetime.now().isoformat()
        self._save_jobs()
        return result

    def start(self):
        """启动调度器后台线程"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="cron_scheduler")
        self._thread.start()
        logger.info(f"[Scheduler] 启动 (检查间隔 {self._check_interval}s, {len(self._jobs)} 个任务)")

    def stop(self):
        self._running = False
        logger.info("[Scheduler] 停止")

    def _loop(self):
        while self._running:
            for job in list(self._jobs.values()):
                try:
                    if job.should_run():
                        self._execute_job(job)
                except Exception as e:
                    logger.warning(f"[Scheduler] 检查任务 {job.job_id} 时出错: {e}")
            time.sleep(self._check_interval)

    def _load_jobs(self):
        if self._jobs_file.exists():
            try:
                data = json.loads(self._jobs_file.read_text(encoding="utf-8"))
                for d in data.get("jobs", []):
                    job = ScheduledJob.from_dict(d)
                    self._jobs[job.job_id] = job
            except Exception as e:
                logger.warning(f"[Scheduler] 加载任务失败: {e}")

    def _save_jobs(self):
        self._jobs_file.parent.mkdir(parents=True, exist_ok=True)
        self._jobs_file.write_text(json.dumps(
            {"jobs": [j.to_dict() for j in self._jobs.values()],
             "updated_at": datetime.now().isoformat()},
            ensure_ascii=False, indent=2), encoding="utf-8")

    def get_stats(self) -> dict:
        return {
            "running": self._running,
            "job_count": len(self._jobs),
            "enabled_count": sum(1 for j in self._jobs.values() if j.enabled),
            "handlers": list(self._handlers.keys()),
            "jobs": [j.to_dict() for j in self._jobs.values()],
        }


# ===== 全局单例 =====
scheduler = CronScheduler()


# ===== 测试 =====
def test():
    s = CronScheduler()

    # 测试自然语言解析
    tests = ["每天 17:00 整理日志", "每天凌晨备份", "每30分钟同步", "每周五检查"]
    for t in tests:
        cron = nl_to_cron(t)
        print(f"  '{t}' -> {cron or '无法解析'}")

    # 测试添加任务
    jid = s.add_from_nl("每天 17:00 整理日志", "daily_cleanup")
    if jid:
        print(f"  任务 ID: {jid}")
        jobs = s.list_jobs()
        print(f"  任务列表: {len(jobs)} 个")
        for j in jobs:
            print(f"    {j['job_id']}: {j['cron_expr']} -> {j['task_desc']}")

    print("[OK] Scheduler 测试通过")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test()
