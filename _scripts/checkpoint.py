#!/usr/bin/env python3
"""
checkpoint.py — ECO AGENT Durable Checkpoint 断点续跑机制

对标 OPENHUMAN 的持久化状态管理：
  执法多步流程（立案→调查→告知→决定→送达）
  每步持久化状态，中断后可恢复。

用法：
  from _scripts.checkpoint import CheckpointManager
  cm = CheckpointManager()
  cp = cm.create("执法审批", {"case_id": "ECO-CASE-2026-0001"})
  cp.step("立案") → cp.step("调查") → cp.step("告知")
  cm.resume(cp.id())  # 中断后恢复
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Any

logger = logging.getLogger("checkpoint")

ROOT = Path(__file__).resolve().parent.parent
CHECKPOINT_DIR = ROOT / "memory-tree" / "obsidian_sync" / "checkpoints"
CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)


class Checkpoint:
    """单个检查点"""

    def __init__(self, cp_id: str, workflow: str, data: dict):
        self._id = cp_id
        self._workflow = workflow
        self._data = dict(data)
        self._steps: list[dict] = []
        self._status = "active"
        self._created = datetime.now().isoformat()
        self._updated = self._created

    @property
    def id(self): return self._id

    @property
    def workflow(self): return self._workflow

    @property
    def status(self): return self._status

    @property
    def steps(self): return list(self._steps)

    def step(self, name: str, result: Any = None) -> "Checkpoint":
        self._steps.append({"name": name, "result": str(result)[:200] if result else None, "time": datetime.now().isoformat()})
        self._updated = datetime.now().isoformat()
        return self

    def complete(self):
        self._status = "completed"
        self._updated = datetime.now().isoformat()

    def fail(self, error: str):
        self._status = "failed"
        self._steps.append({"name": "error", "error": error, "time": datetime.now().isoformat()})
        self._updated = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {"id": self._id, "workflow": self._workflow, "data": self._data, "steps": self._steps, "status": self._status,
                "current_step": len(self._steps), "created": self._created, "updated": self._updated}

    def save(self, directory: Path):
        (directory / f"{self._id}.json").write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


class CheckpointManager:
    """检查点管理器"""

    def __init__(self):
        self._checkpoints: dict[str, Checkpoint] = {}
        self._load_all()

    def create(self, workflow: str, data: dict = None) -> Checkpoint:
        cp_id = f"cp_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(self._checkpoints) + 1}"
        cp = Checkpoint(cp_id, workflow, data or {})
        self._checkpoints[cp_id] = cp
        cp.save(CHECKPOINT_DIR)
        logger.info(f"[CP] 创建: {cp_id} ({workflow})")
        return cp

    def get(self, cp_id: str) -> Checkpoint | None:
        return self._checkpoints.get(cp_id)

    def resume(self, cp_id: str) -> Checkpoint | None:
        cp = self.get(cp_id)
        if not cp:
            logger.warning(f"[CP] 恢复失败，不存在: {cp_id}")
            return None
        if cp.status != "active":
            logger.warning(f"[CP] 恢复失败，状态: {cp.status}")
            return None
        logger.info(f"[CP] 恢复: {cp_id} (步骤 {len(cp.steps)}/{cp.workflow})")
        return cp

    def list_active(self) -> list[Checkpoint]:
        return [cp for cp in self._checkpoints.values() if cp.status == "active"]

    def cleanup_old(self, days: int = 30):
        now = datetime.now()
        removed = 0
        for cp_id, cp in list(self._checkpoints.items()):
            try:
                updated = datetime.fromisoformat(cp.to_dict()["updated"])
                if (now - updated).days > days:
                    path = CHECKPOINT_DIR / f"{cp_id}.json"
                    if path.exists(): path.unlink()
                    del self._checkpoints[cp_id]
                    removed += 1
            except Exception: pass
        if removed:
            logger.info(f"[CP] 清理 {removed} 个过期检查点")

    def _load_all(self):
        for f in sorted(CHECKPOINT_DIR.glob("cp_*.json")):
            try:
                data = json.loads(f.read_text("utf-8", errors="replace"))
                cp = Checkpoint(data["id"], data["workflow"], data.get("data", {}))
                cp._steps = data.get("steps", [])
                cp._status = data.get("status", "active")
                cp._created = data.get("created", "")
                cp._updated = data.get("updated", "")
                self._checkpoints[cp.id] = cp
            except Exception: pass

    def get_stats(self) -> dict:
        statuses = {}
        for cp in self._checkpoints.values():
            s = cp.status
            statuses[s] = statuses.get(s, 0) + 1
        return {"total": len(self._checkpoints), "by_status": statuses}


# ===== 执法案例状态机 =====

class EnforcementFSM:
    """执法程序状态机"""
    STEPS = ["案源登记", "立案审批", "调查取证", "告知听证", "法制审核", "处罚决定", "送达执行", "结案归档"]

    @classmethod
    def _transitions(cls):
        return {cls.STEPS[i]: [cls.STEPS[i + 1]] for i in range(len(cls.STEPS) - 1)}

    def __init__(self, checkpoint_manager: CheckpointManager):
        self._cm = checkpoint_manager

    def start_case(self, case_data: dict) -> Checkpoint:
        return self._cm.create("执法程序", {"case": case_data, "fsm_step": 0})

    def advance(self, cp_id: str) -> dict | None:
        cp = self._cm.resume(cp_id)
        if not cp: return None

        current_step = len(cp.steps)
        if current_step >= len(self.STEPS):
            cp.complete()
            cp.save(CHECKPOINT_DIR)
            return {"status": "completed", "message": "全部步骤已完成"}

        step_name = self.STEPS[current_step]
        cp.step(step_name, {"action": f"执行{step_name}"})
        cp.save(CHECKPOINT_DIR)

        next_steps = self._transitions().get(step_name, [])
        return {"status": "in_progress", "current": step_name, "completed": current_step + 1, "total": len(self.STEPS),
                "next": next_steps[0] if next_steps else None, "checkpoint_id": cp_id}


# ===== 测试 =====

def test():
    cm = CheckpointManager()
    fsm = EnforcementFSM(cm)

    cp = fsm.start_case({"case_title": "XX公司超标排污案", "party": "XX公司"})
    print(f"[TEST] 立案: {cp.id}")

    for i in range(8):
        result = fsm.advance(cp.id)
        if result["status"] == "completed":
            print(f"[TEST] 结案: 全部 {result['completed']} 步完成")
            break
        print(f"  [{result['completed']}/{result['total']}] {result['current']} -> {result['next']}")

    # 模拟中断恢复
    cp2 = cm.get(cp.id)
    assert cp2 is not None and cp2.status == "active"

    stats = cm.get_stats()
    print(f"[TEST] 统计: {stats}")
    print("[OK] Durable Checkpoint 测试通过")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test()
