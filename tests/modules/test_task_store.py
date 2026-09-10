"""任务持久化（对标 WorkBuddy TaskCreate/Update/Get/List + saveTaskFile）单测。

用 tmp_path 隔离存储，验证原子落盘、状态机迁移、终态锁定、列表过滤、并发写不损坏。
"""

from __future__ import annotations

import json
import threading

import pytest

from agent_core import task_store


@pytest.fixture(autouse=True)
def _tmp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(task_store, "BASE", tmp_path)
    yield


def test_create_persists_atomic_file(tmp_path):
    r = task_store.create_task("案卷复核", "核对数据", priority="high", tags=["x"])
    assert r["ok"] is True
    t = r["task"]
    path = tmp_path / f"{t['id']}.json"
    assert path.exists()
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk["status"] == "created"
    assert on_disk["priority"] == "high"
    assert on_disk["history"][0]["status"] == "created"


def test_create_requires_title():
    assert task_store.create_task("  ")["ok"] is False


def test_state_machine_valid_transitions():
    tid = task_store.create_task("t")["task"]["id"]
    assert task_store.update_task(tid, status="in_progress")["ok"]
    assert task_store.update_task(tid, status="paused")["ok"]
    assert task_store.update_task(tid, status="in_progress")["ok"]
    assert task_store.update_task(tid, status="completed")["ok"]
    hist = [h["status"] for h in task_store.get_task(tid)["task"]["history"]]
    assert hist == ["created", "in_progress", "paused", "in_progress", "completed"]


def test_illegal_transition_rejected():
    tid = task_store.create_task("t")["task"]["id"]
    # created → paused 不合法（必须先 in_progress）
    r = task_store.update_task(tid, status="paused")
    assert r["ok"] is False and "非法状态迁移" in r["error"]


def test_terminal_state_locked():
    tid = task_store.create_task("t")["task"]["id"]
    task_store.update_task(tid, status="completed")
    r = task_store.update_task(tid, status="in_progress")
    assert r["ok"] is False


def test_cancel_from_created():
    tid = task_store.create_task("t")["task"]["id"]
    r = task_store.update_task(tid, status="canceled")
    assert r["ok"] and task_store.get_task(tid)["task"]["status"] == "canceled"


def test_get_missing():
    r = task_store.get_task("ghost-x")
    assert r["ok"] is False and "不存在" in r["error"]


def test_update_missing():
    r = task_store.update_task("ghost-x", status="in_progress")
    assert r["ok"] is False


def test_invalid_status_value():
    tid = task_store.create_task("t")["task"]["id"]
    r = task_store.update_task(tid, status="done")
    assert r["ok"] is False and "非法状态" in r["error"]


def test_list_filter_and_counts():
    a = task_store.create_task("a")["task"]["id"]
    task_store.create_task("b")
    task_store.update_task(a, status="in_progress")
    task_store.update_task(a, status="completed")
    allr = task_store.list_tasks()
    assert allr["count"] == 2
    done = task_store.list_tasks(status="completed")
    assert done["count"] == 1 and done["tasks"][0]["id"] == a


def test_path_traversal_rejected():
    with pytest.raises(ValueError):
        task_store._path_for("../../etc/passwd")


def test_concurrent_writes_no_corruption(tmp_path):
    tid = task_store.create_task("并发")["task"]["id"]

    def worker():
        # 交替改优先级与标题（合法字段），每次都应读到完整 JSON
        for i in range(20):
            task_store.update_task(tid, title=f"并发-{i}")

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    # 最终文件必须仍是合法完整 JSON（原子替换保证）
    t = json.loads((tmp_path / f"{tid}.json").read_text(encoding="utf-8"))
    assert t["id"] == tid and t["title"].startswith("并发-")
    # 不得残留 tmp 文件
    assert not list(tmp_path.glob("*.tmp.*"))
