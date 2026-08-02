#!/usr/bin/env python3
"""tests/modules/test_scheduler.py — Cron Scheduler 单元测试"""

import io
import sys
import time
import json
import unittest
from pathlib import Path

# 路径设置
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from agent_core.scheduler import (
    CronScheduler, ScheduledJob, nl_to_cron, NL_TIME_PATTERNS
)


class TestNlToCron(unittest.TestCase):
    def test_exact_patterns(self):
        self.assertEqual(nl_to_cron("每天 17:00 整理日志"), "0 17 * * *")
        self.assertEqual(nl_to_cron("每天 2:00 备份"), "0 2 * * *")
        self.assertEqual(nl_to_cron("每天 9:00 检查"), "0 9 * * *")

    def test_fuzzy_patterns(self):
        self.assertEqual(nl_to_cron("每天凌晨备份"), "0 0 * * *")
        self.assertEqual(nl_to_cron("每30分钟同步"), "*/30 * * * *")

    def test_no_match(self):
        self.assertIsNone(nl_to_cron("下周五提醒我买菜"))


class TestScheduledJob(unittest.TestCase):
    def test_create_job(self):
        job = ScheduledJob("test_1", "0 12 * * *", "测试任务")
        self.assertEqual(job.cron_expr, "0 12 * * *")
        self.assertTrue(job.enabled)

    def test_serialize(self):
        job = ScheduledJob("test_1", "0 12 * * *", "测试任务")
        d = job.to_dict()
        self.assertEqual(d["cron_expr"], "0 12 * * *")
        j2 = ScheduledJob.from_dict(d)
        self.assertEqual(j2.job_id, "test_1")


class TestCronScheduler(unittest.TestCase):
    def setUp(self):
        self.s = CronScheduler()

    def test_add_and_remove_job(self):
        jid = self.s.add_job("0 12 * * *", "测试任务", "test_handler")
        self.assertIsNotNone(jid)
        self.assertIn(jid, self.s._jobs)
        self.assertTrue(self.s.remove_job(jid))
        self.assertNotIn(jid, self.s._jobs)

    def test_add_from_nl(self):
        jid = self.s.add_from_nl("每天 17:00 整理日志", "cleanup")
        self.assertIsNotNone(jid)
        job = self.s._jobs[jid]
        self.assertEqual(job.cron_expr, "0 17 * * *")

    def test_list_jobs(self):
        self.s.add_job("0 8 * * *", "早晨检查")
        self.s.add_job("0 20 * * *", "晚间报告")
        jobs = self.s.list_jobs()
        self.assertEqual(len(jobs), 2)

    def test_register_and_run_handler(self):
        results = []
        def my_handler():
            results.append("done")
            return "ok"

        self.s.register_handler("test", my_handler)
        jid = self.s.add_job("* * * * *", "测试", "test")
        result = self.s.run_job(jid)
        self.assertTrue(result["success"])
        self.assertEqual(len(results), 1)
        self.assertEqual(self.s._jobs[jid].run_count, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
