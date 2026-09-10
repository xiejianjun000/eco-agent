"""任务持久化（对标 WorkBuddy TaskCreate/Update/Get/List + saveTaskFile 原子写）。

实证来源：app.asar cli/dist/codebuddy.js
  · 独立工具集 TaskCreateTool / TaskUpdateTool / TaskGetTool / TaskListTool（不是 system 提示）
  · saveTaskFile：写 `<id>.tmp.<pid>.<timestamp>` → rename，防并发损坏
  · 状态机 CREATED → in_progress → COMPLETED / paused / canceled
  · 调度任务另存 scheduled_tasks.json + .lock（本模块只管用户任务，不管调度）

存储：~/.eco/tasks/items/<id>.json，一任务一文件、tmp→rename 原子落盘。
与既有 task_control.py（mission/commander 运行控制面）分离：那是子进程 steer/stop，
这是 LLM 可直接调用的工作项 CRUD。
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(os.environ.get("ECO_TASK_ITEMS_DIR", "~/.eco/tasks/items")).expanduser()

# 合法状态机（对标 TASK_CREATED / in_progress / COMPLETED / paused / canceled）
STATUS_CREATED = "created"
STATUS_IN_PROGRESS = "in_progress"
STATUS_COMPLETED = "completed"
STATUS_PAUSED = "paused"
STATUS_CANCELED = "canceled"
VALID_STATUSES = {
    STATUS_CREATED, STATUS_IN_PROGRESS, STATUS_COMPLETED, STATUS_PAUSED, STATUS_CANCELED,
}
# 允许的状态迁移（非法迁移拒绝，保证状态机不被乱改）
_ALLOWED = {
    STATUS_CREATED: {STATUS_IN_PROGRESS, STATUS_CANCELED, STATUS_COMPLETED},
    STATUS_IN_PROGRESS: {STATUS_COMPLETED, STATUS_PAUSED, STATUS_CANCELED},
    STATUS_PAUSED: {STATUS_IN_PROGRESS, STATUS_CANCELED, STATUS_COMPLETED},
    STATUS_COMPLETED: set(),
    STATUS_CANCELED: set(),
}

_ID_RE = re.compile(r"[^a-zA-Z0-9_-]")


def _now_ms() -> int:
    return int(time.time() * 1000)


def _iso(ms: int | None = None) -> str:
    ms = ms if ms is not None else _now_ms()
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat(timespec="seconds")


def _slug_title(title: str) -> str:
    s = _ID_RE.sub("-", (title or "").strip().lower())
    s = re.sub(r"-+", "-", s).strip("-")[:24]
    return s or "task"


def _path_for(task_id: str) -> Path:
    # 防路径穿越：id 只允许安全字符
    safe = _ID_RE.sub("", task_id)
    if not safe or safe != task_id:
        raise ValueError(f"非法任务 id: {task_id!r}")
    return BASE / f"{safe}.json"


def atomic_write_task(task: dict) -> None:
    """tmp → rename 原子落盘（对标 saveTaskFile 的 .tmp.<pid>.<timestamp>）。

    并发写同一任务时，tmp 名带 pid+ns 互不覆盖；replace 原子切换，读侧永远只看到完整文件。
    """
    path = _path_for(task["id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}.{time.time_ns()}")
    tmp.write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _read(task_id: str) -> dict | None:
    try:
        return json.loads(_path_for(task_id).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None


# ── CRUD（供工具层调用，返回可 JSON 序列化 dict）──────────────────────
def create_task(title: str, description: str = "", priority: str = "normal",
                tags: list[str] | None = None) -> dict:
    title = (title or "").strip()
    if not title:
        return {"ok": False, "error": "title 不能为空"}
    now = _now_ms()
    task_id = f"{_slug_title(title)}-{uuid.uuid4().hex[:8]}"
    task = {
        "id": task_id,
        "title": title[:120],
        "description": (description or "")[:4000],
        "status": STATUS_CREATED,
        "priority": priority if priority in ("low", "normal", "high") else "normal",
        "tags": [str(t)[:24] for t in (tags or [])][:12],
        "created_ms": now,
        "updated_ms": now,
        "created_at": _iso(now),
        "updated_at": _iso(now),
        "history": [{"status": STATUS_CREATED, "at_ms": now}],
    }
    atomic_write_task(task)
    return {"ok": True, "task": task}


def update_task(task_id: str, status: str | None = None, title: str | None = None,
                description: str | None = None, priority: str | None = None,
                tags: list[str] | None = None) -> dict:
    task = _read(task_id)
    if task is None:
        return {"ok": False, "error": f"任务不存在: {task_id}（先 task_create 或用 task_list 确认 id）"}
    changed: list[str] = []

    if status is not None:
        status = status.strip().lower()
        if status not in VALID_STATUSES:
            return {"ok": False, "error": f"非法状态 {status}；合法值：{sorted(VALID_STATUSES)}"}
        cur = task.get("status", STATUS_CREATED)
        if status != cur:
            if status not in _ALLOWED.get(cur, set()):
                return {"ok": False, "error": f"非法状态迁移 {cur} → {status}"}
            task["status"] = status
            task.setdefault("history", []).append({"status": status, "at_ms": _now_ms()})
            changed.append(f"status={status}")

    if title is not None and title.strip():
        task["title"] = title.strip()[:120]
        changed.append("title")
    if description is not None:
        task["description"] = description[:4000]
        changed.append("description")
    if priority is not None:
        if priority not in ("low", "normal", "high"):
            return {"ok": False, "error": "priority 仅支持 low/normal/high"}
        task["priority"] = priority
        changed.append("priority")
    if tags is not None:
        task["tags"] = [str(t)[:24] for t in tags][:12]
        changed.append("tags")

    if not changed:
        return {"ok": False, "error": "没有需要更新的字段（传 status/title/description/priority/tags）"}
    now = _now_ms()
    task["updated_ms"] = now
    task["updated_at"] = _iso(now)
    atomic_write_task(task)
    return {"ok": True, "task": task, "changed": changed}


def get_task(task_id: str) -> dict:
    task = _read(task_id)
    if task is None:
        return {"ok": False, "error": f"任务不存在: {task_id}"}
    return {"ok": True, "task": task}


def list_tasks(status: str | None = None, limit: int = 50) -> dict:
    items: list[dict] = []
    if BASE.exists():
        for fp in BASE.glob("*.json"):
            try:
                t = json.loads(fp.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue  # 跳过损坏/临时文件，不拖垮列表
            if status and t.get("status") != status:
                continue
            items.append(t)
    # 新建在前
    items.sort(key=lambda t: t.get("created_ms", 0), reverse=True)
    try:
        limit = max(1, min(int(limit), 200))
    except (TypeError, ValueError):
        limit = 50
    items = items[:limit]
    counts: dict[str, int] = {}
    for t in items:
        counts[t.get("status", "?")] = counts.get(t.get("status", "?"), 0) + 1
    return {"ok": True, "count": len(items), "status_counts": counts,
            "tasks": [{"id": t["id"], "title": t.get("title"), "status": t.get("status"),
                       "priority": t.get("priority"), "updated_ms": t.get("updated_ms")}
                      for t in items]}
