#!/usr/bin/env python3
"""
task_control.py — L2 任务调度层运行控制面（P0-2 补全）

对标 Hermes Live Subagent Steering：
- list            : 查看运行中/历史任务（mission 粒度 + 子任务状态）
- steer <id> <instr> : 向运行中的 mission 下发纠偏指令（下一波任务执行前生效）
- stop <id> --keep-partial : 请求停止 mission；已 COMPLETED 子任务保留为部分产出，
                            PENDING 子任务标记 SKIPPED（永不重跑、可审计）

设计要点：
- 控制面与执行进程解耦：执行进程（eco task run / CommanderV2）周期性 poll 控制文件，
  因此 stop/steer 可从任意第二个进程/终端下发。
- 存储为 JSON（registry.json + control.json），写入原子替换，无额外依赖。
"""

import json
import os
import uuid
from datetime import datetime
from pathlib import Path

DEFAULT_BASE = Path(os.environ.get("ECO_TASK_CONTROL_DIR", "~/.eco/tasks")).expanduser()


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _atomic_write(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


class TaskControl:
    """L2 运行控制面：任务注册表 + 外部控制信号。

    执行进程（CommanderV2.execute(control=...)）持有同一实例；控制命令
    （eco task stop/steer）以 registry_dir 定位同一实例即可跨进程生效。
    """

    def __init__(self, base: Path | str | None = None):
        self.base = Path(base) if base else DEFAULT_BASE
        self.registry_path = self.base / "registry.json"
        self.control_path = self.base / "control.json"
        self._mission_id: str | None = None
        self._last_poll = 0.0

    # ── 执行侧 API ────────────────────────────────────────────

    def begin(self, goal: str) -> str:
        """执行进程启动 mission，登记注册表。返回 mission_id。"""
        mid = f"m_{uuid.uuid4().hex[:8]}"
        reg = self._read_registry()
        reg["missions"][mid] = {
            "id": mid,
            "goal": goal,
            "status": "running",
            "pid": os.getpid(),
            "created_at": _now(),
            "updated_at": _now(),
            "tasks": [],
        }
        self._write_registry(reg)
        self._mission_id = mid
        return mid

    def register_tasks(self, mission_id: str, tasks) -> None:
        """登记分解出的子任务（id/description/expectation 快照）。"""
        reg = self._read_registry()
        m = reg["missions"].get(mission_id)
        if m is None:
            return
        existing = {t["id"] for t in m["tasks"]}
        for t in tasks:
            if t.id in existing:
                continue
            m["tasks"].append(
                {
                    "id": t.id,
                    "description": t.description[:120],
                    "status": t.status.value if hasattr(t.status, "value") else str(t.status),
                    "verdict": "",
                }
            )
        self._write_registry(reg)

    def sync_tasks(self, mission_id: str, tasks) -> None:
        """波循环后同步子任务最新状态（含 verdict/error 摘要）。"""
        reg = self._read_registry()
        m = reg["missions"].get(mission_id)
        if m is None:
            return
        by_id = {t["id"]: t for t in m["tasks"]}
        for t in tasks:
            rec = by_id.get(t.id)
            if rec is None:
                continue
            st = t.status.value if hasattr(t.status, "value") else str(t.status)
            if rec["status"] != st:
                rec["status"] = st
            if getattr(t, "verdict", ""):
                rec["verdict"] = t.verdict[:200]
            if getattr(t, "error", ""):
                rec["verdict"] = rec["verdict"] or ""
                rec["error"] = t.error[:200]
        m["updated_at"] = _now()
        if all(rec["status"] in ("completed", "failed", "skipped", "blocked") for rec in m["tasks"]) and m["tasks"]:
            m["status"] = "finished"
        self._write_registry(reg)

    def finish(self, mission_id: str, status: str = "finished", note: str = "") -> None:
        reg = self._read_registry()
        m = reg["missions"].get(mission_id)
        if m is None:
            return
        m["status"] = status
        if note:
            m["note"] = note
        m["updated_at"] = _now()
        self._write_registry(reg)

    def poll(self, mission_id: str) -> dict:
        """波循环开始前调用：读取 stop/steer 控制信号（消费后清除）。"""
        ctl = self._read_control()
        entry = ctl.get("entries", {}).get(mission_id)
        if not entry:
            return {"stop": False, "steer": ""}
        sig = {"stop": bool(entry.get("stop")), "steer": str(entry.get("steer") or "")}
        if sig["stop"] or sig["steer"]:
            ctl["entries"].pop(mission_id, None)
            self._write_control(ctl)
            reg = self._read_registry()
            m = reg["missions"].get(mission_id)
            if m is not None:
                m["note"] = "operator stop (keep-partial)" if sig["stop"] else f"operator steer: {sig['steer'][:120]}"
                self._write_registry(reg)
        return sig

    # ── 控制侧 API（eco task stop/steer 调用，跨进程） ─────────

    def stop(self, mission_id: str, keep_partial: bool = True) -> dict:
        ctl = self._read_control()
        entry = ctl["entries"].setdefault(mission_id, {})
        entry["stop"] = True
        entry["keep_partial"] = keep_partial
        self._write_control(ctl)
        return self._describe(mission_id)

    def steer(self, mission_id: str, instruction: str) -> dict:
        ctl = self._read_control()
        entry = ctl["entries"].setdefault(mission_id, {})
        entry["steer"] = instruction
        self._write_control(ctl)
        return self._describe(mission_id)

    def list_missions(self, limit: int = 20) -> list[dict]:
        reg = self._read_registry()
        ms = list(reg["missions"].values())
        ms.sort(key=lambda x: x["created_at"], reverse=True)
        return ms[:limit]

    def get(self, mission_id: str) -> dict | None:
        return self._read_registry()["missions"].get(mission_id)

    # ── IO ────────────────────────────────────────────────────

    def _read_registry(self) -> dict:
        if not self.registry_path.exists():
            return {"missions": {}}
        try:
            return json.loads(self.registry_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"missions": {}}

    def _write_registry(self, reg: dict) -> None:
        _atomic_write(self.registry_path, reg)

    def _read_control(self) -> dict:
        if not self.control_path.exists():
            return {"entries": {}}
        try:
            return json.loads(self.control_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"entries": {}}

    def _write_control(self, ctl: dict) -> None:
        _atomic_write(self.control_path, ctl)

    def _describe(self, mission_id: str) -> dict:
        m = self.get(mission_id)
        return {"mission_id": mission_id, "found": m is not None, "status": (m or {}).get("status", "unknown")}


def _demo_goal() -> str:
    return (
        "整理一份《RAG 系统生产化》技术方案：1) 列出 RAG 检索链路 6 个关键环节 "
        "2) 每环节给出 2 种主流实现与取舍 3) 输出部署架构建议与监控指标清单"
    )
