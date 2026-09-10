"""任务工具注册（对标 WorkBuddy TaskCreate/Update/Get/List 独立工具集）。

L2 风险（本地工作态文件写入，落在 ~/.eco/tasks/items/ 安全区，不碰业务文件）。
幂等：register_task_tools 重复调用不重复注册。
"""

from __future__ import annotations

import json
import logging

from agent_core import task_store

log = logging.getLogger(__name__)

_DONE = False


def _j(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _task_create(title: str = "", description: str = "", priority: str = "normal",
                 tags=None) -> str:
    return _j(task_store.create_task(title, description, priority, tags))


def _task_update(task_id: str = "", status: str | None = None, title: str | None = None,
                 description: str | None = None, priority: str | None = None,
                 tags=None) -> str:
    return _j(task_store.update_task(task_id, status, title, description, priority, tags))


def _task_get(task_id: str = "") -> str:
    return _j(task_store.get_task(task_id))


def _task_list(status: str = "", limit: int = 50) -> str:
    return _j(task_store.list_tasks(status or None, limit))


def register_task_tools() -> None:
    global _DONE
    if _DONE:
        return
    from agent_core.tools_registry import register_external_tool

    register_external_tool(
        name="task_create",
        description=(
            "创建一个可持久化追踪的任务（工作项），立即落盘并返回 task id。"
            "用于多步骤/跨轮次工作：先建任务，再用 task_update 推进状态。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "任务标题（简短）"},
                "description": {"type": "string", "description": "任务详情/验收标准"},
                "priority": {"type": "string", "enum": ["low", "normal", "high"],
                             "description": "优先级，默认 normal"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "标签"},
            },
            "required": ["title"],
        },
        handler=_task_create,
        risk_level="L2",
        source="builtin-tasks",
    )

    register_external_tool(
        name="task_update",
        description=(
            "更新任务状态或内容。状态机：created→in_progress→completed/paused/canceled；"
            "completed/canceled 为终态。非法迁移会被拒绝。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "task_create 返回的 id"},
                "status": {"type": "string",
                           "enum": ["created", "in_progress", "completed", "paused", "canceled"]},
                "title": {"type": "string"},
                "description": {"type": "string"},
                "priority": {"type": "string", "enum": ["low", "normal", "high"]},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["task_id"],
        },
        handler=_task_update,
        risk_level="L2",
        source="builtin-tasks",
    )

    register_external_tool(
        name="task_get",
        description="按 id 查询单个任务的完整内容、状态与状态迁移历史。",
        parameters={
            "type": "object",
            "properties": {"task_id": {"type": "string"}},
            "required": ["task_id"],
        },
        handler=_task_get,
        risk_level="L1",
        source="builtin-tasks",
    )

    register_external_tool(
        name="task_list",
        description="列出任务（可按 status 过滤），返回标题/状态/优先级与状态计数。",
        parameters={
            "type": "object",
            "properties": {
                "status": {"type": "string",
                           "enum": ["created", "in_progress", "completed", "paused", "canceled"]},
                "limit": {"type": "integer"},
            },
        },
        handler=_task_list,
        risk_level="L1",
        source="builtin-tasks",
    )
    _DONE = True
    log.info("[tasks] 任务工具已注册: task_create/update/get/list")
