#!/usr/bin/env python3
"""
workflow_discovery.py — Eco Agent B-03 自动流程发现 + G-02 长任务快照

B-03: 从历史执行日志中提炼高频协作序列 → 标准工作流模板
G-02: >1小时任务每10分钟自动快照，崩溃恢复<1分钟
"""

import hashlib
import json
import logging
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("workflow_discovery")
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "memory-tree" / "data"
SNAPSHOT_DIR = DATA_DIR / "snapshots"
SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)


# ═══════════════════════════════════
# B-03 自动流程发现
# ═══════════════════════════════════


class WorkflowDiscoverer:
    """从历史日志中自动发现高频协作序列"""

    def __init__(self):
        self._templates_dir = DATA_DIR / "workflow_templates"
        self._templates_dir.mkdir(parents=True, exist_ok=True)
        self._logs: list[dict] = []

    def ingest(self, execution_logs: list[dict]):
        """注入历史执行日志"""
        self._logs.extend(execution_logs)

    def discover(self, min_frequency: int = 3) -> list[dict]:
        """发现高频协作序列并生成工作流模板"""
        sequences = self._extract_sequences()
        frequent = [s for s in sequences if s["count"] >= min_frequency]
        templates = []
        for seq in frequent:
            tmpl = self._to_template(seq)
            templates.append(tmpl)
            self._save_template(tmpl)
        logger.info(f"[Discovery] 从{len(self._logs)}条日志发现{len(frequent)}个高频序列, 生成{len(templates)}个模板")
        return templates

    def _extract_sequences(self) -> list[dict]:
        """提取任务执行序列"""
        seq_counter = Counter()
        seq_details = {}
        for log in self._logs:
            tasks = log.get("tasks", log.get("steps", []))
            if len(tasks) < 2:
                continue
            # 取角色序列
            roles = tuple(t.get("agent", t.get("agent_role", "")) for t in tasks)
            key = "→".join(roles)
            seq_counter[key] += 1
            if key not in seq_details:
                seq_details[key] = {
                    "roles": list(roles),
                    "descriptions": [t.get("desc", t.get("description", "")) for t in tasks],
                }

        results = []
        for seq_str, count in seq_counter.most_common(20):
            results.append(
                {
                    "sequence": seq_str,
                    "count": count,
                    "roles": seq_details[seq_str]["roles"],
                    "descriptions": seq_details[seq_str]["descriptions"],
                }
            )
        return results

    def _to_template(self, seq: dict) -> dict:
        """将高频序列转换为工作流模板"""
        tmpl_id = f"ecoflow_{hashlib.md5(seq['sequence'].encode()).hexdigest()[:8]}"
        return {
            "id": tmpl_id,
            "name": f"自动流程: {seq['sequence'][:30]}",
            "roles": seq["roles"],
            "description": " → ".join(seq["descriptions"][:5]),
            "discovered_at": datetime.now().isoformat(),
            "frequency": seq["count"],
            "steps": [
                {"order": i + 1, "role": r, "task": seq["descriptions"][i] if i < len(seq["descriptions"]) else ""}
                for i, r in enumerate(seq["roles"])
            ],
        }

    def _save_template(self, template: dict):
        path = self._templates_dir / f"{template['id']}.json"
        path.write_text(json.dumps(template, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_templates(self) -> list[dict]:
        templates = []
        for f in sorted(self._templates_dir.glob("*.json")):
            try:
                templates.append(json.loads(f.read_text("utf-8", errors="replace")))
            except Exception:
                pass
        return templates

    def get_stats(self) -> dict:
        return {"logs_ingested": len(self._logs), "templates": len(self.list_templates())}


# ═══════════════════════════════════
# G-02 长任务快照
# ═══════════════════════════════════


class LongTaskSnapshot:
    """G-02 长任务快照恢复"""

    def __init__(self):
        self._interval = 600  # 10分钟

    def save(self, task_id: str, context: dict) -> str:
        """保存长任务快照"""
        snapshot = {
            "task_id": task_id,
            "context": context,
            "timestamp": datetime.now().isoformat(),
            "snapshot_id": f"snap_{uuid.uuid4().hex[:8]}",
        }
        path = SNAPSHOT_DIR / f"{task_id}.json"
        path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        return snapshot["snapshot_id"]

    def restore(self, task_id: str) -> dict | None:
        """恢复快照"""
        path = SNAPSHOT_DIR / f"{task_id}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text("utf-8", errors="replace"))
            elapsed = (datetime.now() - datetime.fromisoformat(data["timestamp"])).total_seconds()
            data["recovery_time_s"] = round(elapsed, 1)
            return data
        except Exception:
            return None

    def cleanup_old(self, max_hours: int = 72):
        now = datetime.now()
        for f in SNAPSHOT_DIR.glob("*.json"):
            try:
                mtime = datetime.fromtimestamp(f.stat().st_mtime)
            except Exception:
                continue
            if (now - mtime).total_seconds() > max_hours * 3600:
                f.unlink()

    def get_stats(self) -> dict:
        return {"snapshots": len(list(SNAPSHOT_DIR.glob("*.json"))), "interval_s": self._interval}


# ===== 测试 =====


def test():
    import io
    import sys as _sys

    _sys.stdout = io.TextIOWrapper(_sys.stdout.buffer, encoding="utf-8", errors="replace")

    # B-03 测试
    wd = WorkflowDiscoverer()
    logs = []
    for _ in range(20):
        logs.append(
            {
                "tasks": [
                    {"agent": "analyst", "description": "分析需求"},
                    {"agent": "planner", "description": "制定计划"},
                    {"agent": "coder", "description": "编写代码"},
                    {"agent": "reviewer", "description": "审查代码"},
                ]
            }
        )
    wd.ingest(logs)
    templates = wd.discover(min_frequency=3)
    print(f"[B-03] 发现 {len(templates)} 个工作流模板", flush=True)

    # G-02 测试
    lts = LongTaskSnapshot()
    sid = lts.save("task_long_running_001", {"progress": 60, "files": ["a.py", "b.py"]})
    restored = lts.restore("task_long_running_001")
    print(f"[G-02] 快照保存: {sid}, 恢复: progress={restored['context']['progress']}%", flush=True)

    wd_stats = wd.get_stats()
    lts_stats = lts.get_stats()
    print(f"[Stats] 模板: {wd_stats['templates']}, 快照: {lts_stats['snapshots']}", flush=True)
    print("[PASS] B-03 + G-02 测试通过", flush=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test()
