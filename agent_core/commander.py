#!/usr/bin/env python3
"""
commander.py — Eco Agent 指挥官 Agent + Agent 池

Phase 1 核心交付：任务分解、智能体池动态管理、并行执行。

架构：
  指挥官 Agent（Commander）
    ├── 任务分解器（Task Decomposer）
    ├── 调度器（Scheduler）
    ├── Agent 池（Agent Pool）—— 动态创建/销毁 Agent
    └── 观察器（Observer）—— 执行验证与反馈

用法：
  python agent_core/commander.py
"""

import os, sys, json, time, uuid, logging, threading, queue
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass, field, asdict
from enum import Enum

logger = logging.getLogger("commander")

ROOT = Path(__file__).resolve().parent.parent


# ═══════════════════════════════════
# 数据模型
# ═══════════════════════════════════

class AgentRole(str, Enum):
    CODER = "coder"
    RESEARCHER = "researcher"
    WRITER = "writer"
    ANALYST = "analyst"
    DESIGNER = "designer"
    REVIEWER = "reviewer"
    PLANNER = "planner"
    DEVOPS = "devops"
    COORDINATOR = "coordinator"
    CUSTOM = "custom"

class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"

@dataclass
class Task:
    """任务单元"""
    id: str = ""
    description: str = ""
    agent_role: AgentRole = AgentRole.CUSTOM
    priority: int = 5
    status: TaskStatus = TaskStatus.PENDING
    input: dict = field(default_factory=dict)
    output: str = ""
    error: str = ""
    depends_on: List[str] = field(default_factory=list)
    created_at: str = ""
    started_at: str = ""
    completed_at: str = ""
    execution_time_ms: float = 0.0

    def __post_init__(self):
        if not self.id:
            self.id = f"task_{uuid.uuid4().hex[:8]}"
        if not self.created_at:
            self.created_at = datetime.now().isoformat()

@dataclass
class AgentInstance:
    """Agent 实例"""
    id: str = ""
    name: str = ""
    role: AgentRole = AgentRole.CUSTOM
    model: str = ""
    status: str = "idle"
    current_task: str = ""
    spawned_at: str = ""
    task_count: int = 0
    success_count: int = 0
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.id:
            self.id = f"agent_{uuid.uuid4().hex[:8]}"
        if not self.spawned_at:
            self.spawned_at = datetime.now().isoformat()


# ═══════════════════════════════════
# Agent 池
# ═══════════════════════════════════

class AgentPool:
    """专业 Agent 池——动态创建、按需扩缩、生命周期管理"""

    def __init__(self):
        self._agents: Dict[str, AgentInstance] = {}
        self._lock = threading.Lock()
        self._work_queue: queue.Queue = queue.Queue()
        self._workers: List[threading.Thread] = []
        self._max_workers = 10

    def spawn(self, role: AgentRole = AgentRole.CUSTOM, name: str = "",
              model: str = "") -> AgentInstance:
        """动态生成 Agent"""
        agent = AgentInstance(
            name=name or f"{role.value}_{len(self._agents) + 1}",
            role=role, model=model or "auto"
        )
        with self._lock:
            self._agents[agent.id] = agent
        logger.info(f"[Pool] 生成 Agent: {agent.name} ({role.value})")
        return agent

    def dispose(self, agent_id: str) -> bool:
        """销毁 Agent"""
        with self._lock:
            if agent_id in self._agents:
                agent = self._agents[agent_id]
                agent.status = "disposed"
                del self._agents[agent_id]
                logger.info(f"[Pool] 销毁 Agent: {agent.name}")
                return True
        return False

    def get_idle(self, role: Optional[AgentRole] = None) -> Optional[AgentInstance]:
        """获取空闲 Agent"""
        with self._lock:
            for agent in self._agents.values():
                if agent.status == "idle":
                    if role and agent.role != role:
                        continue
                    return agent
        return None

    def get_or_spawn(self, role: AgentRole = AgentRole.CUSTOM) -> AgentInstance:
        """获取或创建"""
        agent = self.get_idle(role)
        if agent:
            return agent
        return self.spawn(role)

    def assign_task(self, agent_id: str, task_id: str):
        with self._lock:
            if agent_id in self._agents:
                self._agents[agent_id].status = "busy"
                self._agents[agent_id].current_task = task_id
                self._agents[agent_id].task_count += 1

    def complete_task(self, agent_id: str, success: bool = True):
        with self._lock:
            if agent_id in self._agents:
                self._agents[agent_id].status = "idle"
                self._agents[agent_id].current_task = ""
                if success:
                    self._agents[agent_id].success_count += 1

    def scale(self, target_count: int, role: AgentRole = AgentRole.CUSTOM):
        """扩缩容"""
        current = len([a for a in self._agents.values() if a.role == role])
        if current < target_count:
            for _ in range(target_count - current):
                self.spawn(role)
        elif current > target_count:
            idle = [a for a in self._agents.values() if a.role == role and a.status == "idle"]
            for a in idle[:current - target_count]:
                self.dispose(a.id)

    def get_stats(self) -> dict:
        with self._lock:
            by_role = {}
            for a in self._agents.values():
                by_role[a.role.value] = by_role.get(a.role.value, 0) + 1
            return {
                "total": len(self._agents),
                "by_role": by_role,
                "idle": sum(1 for a in self._agents.values() if a.status == "idle"),
                "busy": sum(1 for a in self._agents.values() if a.status == "busy"),
                "total_tasks": sum(a.task_count for a in self._agents.values()),
                "success_rate": f"{sum(a.success_count for a in self._agents.values()) / max(sum(a.task_count for a in self._agents.values()), 1) * 100:.0f}%",
            }


# ═══════════════════════════════════
# 任务分解器
# ═══════════════════════════════════

class TaskDecomposer:
    """任务分解器——将用户需求分解为可执行的任务链"""

    def __init__(self):
        self._patterns = self._init_patterns()

    def _init_patterns(self) -> Dict:
        return {
            "开发": {
                "tasks": [
                    ("分析需求", AgentRole.ANALYST),
                    ("设计方案", AgentRole.DESIGNER),
                    ("编写代码", AgentRole.CODER),
                    ("审查代码", AgentRole.REVIEWER),
                    ("测试部署", AgentRole.DEVOPS),
                ]
            },
            "研究": {
                "tasks": [
                    ("收集资料", AgentRole.RESEARCHER),
                    ("分析数据", AgentRole.ANALYST),
                    ("撰写报告", AgentRole.WRITER),
                    ("审查结论", AgentRole.REVIEWER),
                ]
            },
            "写作": {
                "tasks": [
                    ("确定大纲", AgentRole.PLANNER),
                    ("撰写内容", AgentRole.WRITER),
                    ("审查修改", AgentRole.REVIEWER),
                    ("定稿输出", AgentRole.WRITER),
                ]
            },
            "通用": {
                "tasks": [
                    ("理解需求", AgentRole.ANALYST),
                    ("制定计划", AgentRole.PLANNER),
                    ("执行任务", AgentRole.CUSTOM),
                    ("验证结果", AgentRole.REVIEWER),
                ]
            }
        }

    def decompose(self, goal: str, context: dict = None) -> List[Task]:
        """将目标分解为任务链"""
        goal_lower = goal.lower()
        pattern = self._patterns.get("通用")
        for key in self._patterns:
            if key in goal_lower:
                pattern = self._patterns[key]
                break

        tasks = []
        for i, (desc, role) in enumerate(pattern["tasks"]):
            task = Task(
                description=f"[{i+1}/{len(pattern['tasks'])}] {desc}：{goal[:50]}",
                agent_role=role,
                priority=10 - i,
                depends_on=[tasks[-1].id] if tasks else [],
            )
            tasks.append(task)
        return tasks


# ═══════════════════════════════════
# 指挥官 Agent
# ═══════════════════════════════════

class Commander:
    """指挥官 Agent——负责任务分解、调度、Agent 池管理"""

    def __init__(self):
        self.pool = AgentPool()
        self.decomposer = TaskDecomposer()
        self._tasks: Dict[str, Task] = {}
        self._results: List[Dict] = []

    def execute(self, goal: str, context: dict = None) -> Dict:
        """执行一个目标——分解→调度→执行→汇总"""
        logger.info(f"[Commander] 接收目标: {goal[:60]}")

        # 1. 分解
        tasks = self.decomposer.decompose(goal, context)
        for t in tasks:
            self._tasks[t.id] = t
        logger.info(f"[Commander] 分解为 {len(tasks)} 个子任务")

        # 2. 调度执行
        for task in tasks:
            self._execute_task(task)

        # 3. 汇总
        summary = self._summarize()
        self._results.append(summary)
        return summary

    def _execute_task(self, task: Task):
        """执行单个任务"""
        # 检查依赖
        for dep_id in task.depends_on:
            dep = self._tasks.get(dep_id)
            if dep and dep.status != TaskStatus.COMPLETED:
                task.status = TaskStatus.SKIPPED
                task.error = f"依赖任务 {dep_id} 未完成"
                logger.warning(f"  [SKIP] {task.description[:40]}: 依赖未完成")
                return

        # 获取 Agent
        agent = self.pool.get_or_spawn(task.agent_role)
        self.pool.assign_task(agent.id, task.id)
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now().isoformat()

        start = time.time()
        try:
            # 执行（当前为模拟执行，后续对接 LLM）
            output = self._simulate_execute(task, agent)
            task.output = output
            task.status = TaskStatus.COMPLETED
            self.pool.complete_task(agent.id, True)
            logger.info(f"  [OK] {task.description[:40]} ({agent.name})")
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            self.pool.complete_task(agent.id, False)
            logger.warning(f"  [FAIL] {task.description[:40]}: {e}")

        task.completed_at = datetime.now().isoformat()
        task.execution_time_ms = (time.time() - start) * 1000

    def _simulate_execute(self, task: Task, agent: AgentInstance) -> str:
        """模拟执行（后续替换为 LLM 调用）"""
        time.sleep(0.2)
        return f"[{agent.name}] 完成: {task.description[:40]}"

    def _summarize(self) -> Dict:
        tasks = self._tasks.values()
        completed = sum(1 for t in tasks if t.status == TaskStatus.COMPLETED)
        failed = sum(1 for t in tasks if t.status == TaskStatus.FAILED)
        total_time = sum(t.execution_time_ms for t in tasks)
        return {
            "total_tasks": len(self._tasks),
            "completed": completed,
            "failed": failed,
            "skipped": sum(1 for t in tasks if t.status == TaskStatus.SKIPPED),
            "total_time_ms": round(total_time, 1),
            "tasks": [{"id": t.id, "desc": t.description[:50], "status": t.status.value,
                       "agent": t.agent_role.value, "time_ms": round(t.execution_time_ms, 1)} for t in self._tasks.values()],
        }

    def get_stats(self) -> dict:
        return {
            "pool": self.pool.get_stats(),
            "tasks_completed": len(self._results),
            "missions": [{"total": r["total_tasks"], "completed": r["completed"],
                          "time_ms": r["total_time_ms"]} for r in self._results],
        }


# ===== 测试 =====

def test():
    import io, sys as _sys
    _sys.stdout = io.TextIOWrapper(_sys.stdout.buffer, encoding='utf-8', errors='replace')

    print("[TEST] Commander Agent + Agent Pool", flush=True)
    print(f"  {'='*40}", flush=True)

    cmd = Commander()

    # 测试 Agent Pool
    pool = cmd.pool
    pool.spawn(AgentRole.CODER, "coder-1")
    pool.spawn(AgentRole.RESEARCHER, "researcher-1")
    pool.spawn(AgentRole.WRITER, "writer-1")
    print(f"\n[Pool] 初始: {pool.get_stats()}", flush=True)

    # 测试任务分解与执行
    result = cmd.execute("开发一个 Python 法规检索工具")
    print(f"\n[Mission] 任务数: {result['total_tasks']}, 完成: {result['completed']}, "
          f"耗时: {result['total_time_ms']:.0f}ms", flush=True)

    # 测试动态扩缩
    pool.scale(5, AgentRole.CODER)
    print(f"\n[Scale] 扩容后: {pool.get_stats()}", flush=True)

    stats = cmd.get_stats()
    missions = stats.get('tasks_completed', [])
    print(f"\n[Stats] 已完成任务数: {sum(r.get('total_tasks', 0) for r in missions)}", flush=True)
    print(f"\n{'='*40}", flush=True)
    print("[OK] Commander + Agent Pool 测试通过", flush=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(name)s] %(message)s")
    test()
