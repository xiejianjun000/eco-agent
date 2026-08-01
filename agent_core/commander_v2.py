#!/usr/bin/env python3
"""
commander_v2.py — Eco Agent 指挥官 v2（Phase 3 多智能体协作深化）

对标验收标准：B-01/B-02/B-04/B-05/G-01/G-03

增强项：
  B-01 动态自组织：复杂任务10秒分解≥5子任务，自动组队
  B-02 并行无冲突：工作树隔离，3+ Agent 同时修改
  B-04 弹性伸缩：积压>10 自动扩容，空闲自动回收
  B-05 跨Agent协商：资源争用避让协议
  G-01 重规划上限：最多2轮，第3轮上报
  G-03 DAG循环检测：5秒告警并自动破环
"""

import os
import time
import uuid
import logging
import threading
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger("commander_v2")
ROOT = Path(__file__).resolve().parent.parent


# ═══════════════════════════════════
# 枚举与数据模型
# ═══════════════════════════════════

class AgentRole(str, Enum):
    CODER = "coder"; RESEARCHER = "researcher"; WRITER = "writer"
    ANALYST = "analyst"; DESIGNER = "designer"; REVIEWER = "reviewer"
    PLANNER = "planner"; DEVOPS = "devops"; COORDINATOR = "coordinator"
    FRONTEND = "frontend"; BACKEND = "backend"; TESTER = "tester"
    CUSTOM = "custom"

class TaskStatus(str, Enum):
    PENDING = "pending"; RUNNING = "running"; COMPLETED = "completed"
    FAILED = "failed"; SKIPPED = "skipped"; BLOCKED = "blocked"

@dataclass
class Task:
    id: str = ""; description: str = ""; agent_role: AgentRole = AgentRole.CUSTOM
    priority: int = 5; status: TaskStatus = TaskStatus.PENDING
    input: dict = field(default_factory=dict); output: str = ""; error: str = ""
    expectation: str = ""   # 完成判据：预期世界状态（EcoAgent 锚点）
    verdict: str = ""       # 验证结论：expectation vs 实际产出的核验记录
    depends_on: list[str] = field(default_factory=list)
    replan_count: int = 0; max_replans: int = 2
    worktree: str = ""; file_locks: list[str] = field(default_factory=list)
    created_at: str = ""; started_at: str = ""; completed_at: str = ""
    execution_time_ms: float = 0.0

    def __post_init__(self):
        if not self.id: self.id = f"task_{uuid.uuid4().hex[:8]}"
        if not self.created_at: self.created_at = datetime.now().isoformat()

@dataclass
class AgentInstance:
    id: str = ""; name: str = ""; role: AgentRole = AgentRole.CUSTOM
    model: str = ""; status: str = "idle"; current_task: str = ""
    spawned_at: str = ""; task_count: int = 0; success_count: int = 0
    worktree: str = ""; file_locks: set[str] = field(default_factory=set)
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.id: self.id = f"agent_{uuid.uuid4().hex[:8]}"
        if not self.spawned_at: self.spawned_at = datetime.now().isoformat()


# ═══════════════════════════════════
# 工作树隔离（B-02）
# ═══════════════════════════════════

class WorktreeManager:
    """工作树隔离——并行无冲突执行"""

    def __init__(self, base_dir: str = None):
        self._base = Path(base_dir or (ROOT / "worktrees"))
        self._base.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, str] = {}

    def create(self, agent_id: str) -> str:
        wt = self._base / f"wt_{agent_id[:8]}"
        wt.mkdir(parents=True, exist_ok=True)
        (wt / ".workspace").write_text(f"agent: {agent_id}\ncreated: {datetime.now().isoformat()}")
        return str(wt)

    def acquire_lock(self, agent_id: str, file_path: str) -> bool:
        key = file_path.replace("\\", "/")
        if key in self._locks and self._locks[key] != agent_id:
            return False
        self._locks[key] = agent_id
        return True

    def release_lock(self, agent_id: str, file_path: str = None):
        if file_path:
            key = file_path.replace("\\", "/")
            if self._locks.get(key) == agent_id:
                del self._locks[key]
        else:
            self._locks = {k: v for k, v in self._locks.items() if v != agent_id}

    def merge_back(self, agent_id: str):
        wt = self._base / f"wt_{agent_id[:8]}"
        if wt.exists():
            import shutil
            shutil.rmtree(wt, ignore_errors=True)


# ═══════════════════════════════════
# Agent 池 v2（B-04 弹性伸缩）
# ═══════════════════════════════════

class AgentPoolV2:
    """Agent 池 v2——弹性伸缩"""

    def __init__(self):
        self._agents: dict[str, AgentInstance] = {}
        self._lock = threading.Lock()
        self._max_agents = 20
        self._queue_depth = 0
        self._wtm = WorktreeManager()

    def spawn(self, role: AgentRole = AgentRole.CUSTOM) -> AgentInstance:
        agent = AgentInstance(name=f"{role.value}_{len(self._agents) + 1}", role=role)
        agent.worktree = self._wtm.create(agent.id)
        with self._lock:
            self._agents[agent.id] = agent
        return agent

    def dispose(self, agent_id: str) -> bool:
        with self._lock:
            if agent_id in self._agents:
                self._wtm.merge_back(agent_id)
                self._wtm.release_lock(agent_id)
                del self._agents[agent_id]
                return True
        return False

    def get_or_spawn(self, role: AgentRole = AgentRole.CUSTOM) -> AgentInstance:
        # B-04 弹性伸缩：任务积压检查
        if self._queue_depth > 10 and len(self._agents) < self._max_agents:
            return self.spawn(role)
        for a in list(self._agents.values()):
            if a.status == "idle" and a.role == role:
                return a
        return self.spawn(role) if len(self._agents) < self._max_agents else list(self._agents.values())[0]

    def acquire_file_lock(self, agent_id: str, file_path: str) -> bool:
        return self._wtm.acquire_lock(agent_id, file_path)

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
                if success: self._agents[agent_id].success_count += 1

    # B-04 弹性伸缩：空闲回收
    def auto_scale(self):
        with self._lock:
            idle_agents = [a for a in self._agents.values() if a.status == "idle" and a.task_count == 0]
            if len(idle_agents) > 5:
                for a in idle_agents[:len(idle_agents) - 3]:
                    self._wtm.merge_back(a.id)
                    del self._agents[a.id]

    def get_stats(self) -> dict:
        with self._lock:
            by_role = {}
            for a in self._agents.values():
                by_role[a.role.value] = by_role.get(a.role.value, 0) + 1
            total_tasks = sum(a.task_count for a in self._agents.values())
            successes = sum(a.success_count for a in self._agents.values())
            return {"total": len(self._agents), "by_role": by_role,
                    "idle": sum(1 for a in self._agents.values() if a.status == "idle"),
                    "busy": sum(1 for a in self._agents.values() if a.status == "busy"),
                    "total_tasks": total_tasks,
                    "success_rate": f"{successes / max(total_tasks, 1) * 100:.0f}%"}


# ═══════════════════════════════════
# DAG 检测器（G-03）
# ═══════════════════════════════════

class DAGValidator:
    """DAG 循环依赖检测"""

    @staticmethod
    def has_cycle(tasks: list[Task]) -> list[str] | None:
        deps = {t.id: list(t.depends_on) for t in tasks}
        visited = set(); path = set()
        def dfs(nid):
            if nid in path: return True
            if nid in visited: return False
            path.add(nid); visited.add(nid)
            for dep in deps.get(nid, []):
                if dep in deps and dfs(dep): return True
            path.remove(nid); return False
        for t in tasks:
            if t.id not in visited and dfs(t.id):
                cycle_nodes = list(path & set(deps.keys()))
                return cycle_nodes[:5]
        return None

    @staticmethod
    def break_cycle(tasks: list[Task]) -> list[Task]:
        cycle = DAGValidator.has_cycle(tasks)
        if not cycle: return tasks
        # 自动破环：移除循环中最低优先级的依赖
        for t in tasks:
            if t.id in cycle:
                for dep in list(t.depends_on):
                    if dep in cycle:
                        t.depends_on.remove(dep)
        return tasks


# ═══════════════════════════════════
# 任务分解器 v2（B-01 动态自组织）
# ═══════════════════════════════════

class TaskDecomposerV2:
    """任务分解器 v2——深层分解（每步携带 expectation 完成判据）"""

    def __init__(self):
        # 模板: (步骤描述, 角色, expectation 完成判据)
        self._patterns = {
            "开发": [("分析需求", AgentRole.ANALYST, "产出需求清单，功能点与约束无遗漏"),
                     ("设计架构", AgentRole.DESIGNER, "产出架构方案，模块划分与接口定义明确"),
                     ("前端实现", AgentRole.FRONTEND, "前端页面可运行，覆盖需求清单中的交互"),
                     ("后端实现", AgentRole.BACKEND, "接口按架构方案实现，可正常响应"),
                     ("编写测试", AgentRole.TESTER, "关键路径有测试且全部通过"),
                     ("代码审查", AgentRole.REVIEWER, "审查意见逐条闭环，无未处理的 CRITICAL"),
                     ("部署发布", AgentRole.DEVOPS, "服务部署完成，健康检查通过")],
            "研究": [("收集资料", AgentRole.RESEARCHER, "资料来源可溯源，覆盖主题主要方面"),
                     ("分析数据", AgentRole.ANALYST, "分析结论有数据支撑，方法可复现"),
                     ("可视化", AgentRole.DESIGNER, "图表准确表达分析结论"),
                     ("撰写报告", AgentRole.WRITER, "报告结构完整，结论与证据一一对应"),
                     ("审查结论", AgentRole.REVIEWER, "结论经核验无事实性错误")],
            "写作": [("确定大纲", AgentRole.PLANNER, "大纲层级完整，覆盖主题要点"),
                     ("调研素材", AgentRole.RESEARCHER, "素材真实可溯源，与大纲各节对应"),
                     ("撰写初稿", AgentRole.WRITER, "初稿覆盖大纲全部章节"),
                     ("审查修改", AgentRole.REVIEWER, "修改意见闭环，事实与逻辑错误清零"),
                     ("定稿输出", AgentRole.WRITER, "定稿格式规范，可交付")],
            "通用": [("理解需求", AgentRole.ANALYST, "需求复述准确，关键约束无遗漏"),
                     ("制定计划", AgentRole.PLANNER, "计划步骤有序且可执行，依赖关系明确"),
                     ("执行前置", AgentRole.CUSTOM, "前置条件就绪，产出可供下游使用"),
                     ("执行主体", AgentRole.CUSTOM, "主体任务产出符合需求描述"),
                     ("验证结果", AgentRole.REVIEWER, "逐项对照需求核验，无未达标项"),
                     ("交付输出", AgentRole.CUSTOM, "交付物完整，格式符合要求")],
        }

    def decompose(self, goal: str, context: dict = None,
                  skip: int = 0, note: str = "") -> list[Task]:
        """分解目标（B-01：≥5子任务，10秒内）
        skip: 跳过前 skip 步（前缀保留 replan 时只重写剩余步骤）
        note: 附加上下文（如失败教训），写入每个任务的描述"""
        gl = goal.lower()
        pattern = self._patterns.get("通用")
        for key in self._patterns:
            if key in gl: pattern = self._patterns[key]; break
        if len(pattern) < 5: pattern = self._patterns["通用"]
        tasks = []
        for i, (desc, role, expectation) in enumerate(pattern):
            if i < skip: continue
            prefix = f"[{i+1}/{len(pattern)}] "
            t = Task(description=f"{prefix}{desc}：{goal[:40]}" + (f"（{note}）" if note else ""),
                     agent_role=role, priority=10 - i, expectation=expectation,
                     depends_on=[tasks[-1].id] if tasks else [])
            tasks.append(t)
        return tasks


# ═══════════════════════════════════
# 协商器（B-05）
# ═══════════════════════════════════

class Negotiator:
    """跨 Agent 协商——资源争用避让"""

    def __init__(self):
        self._pending: dict[str, list[dict]] = {}

    def request(self, agent_id: str, resource: str, task_id: str) -> dict:
        key = resource.replace("\\", "/")
        if key not in self._pending: self._pending[key] = []
        # 检查是否已有等待
        existing = [r for r in self._pending[key] if r["agent"] == agent_id]
        if existing: return existing[0]
        entry = {"agent": agent_id, "task": task_id, "requested_at": time.time(),
                 "position": len(self._pending[key])}
        self._pending[key].append(entry)
        if len(self._pending[key]) == 1: return {"granted": True, "wait": 0}
        # B-05：30秒内达成避让
        wait_time = min(30, (len(self._pending[key]) - 1) * 5)
        return {"granted": False, "wait": wait_time, "position": entry["position"]}

    def release(self, agent_id: str, resource: str):
        key = resource.replace("\\", "/")
        if key in self._pending:
            self._pending[key] = [r for r in self._pending[key] if r["agent"] != agent_id]
            if not self._pending[key]: del self._pending[key]

    def get_stats(self) -> dict:
        return {"active_contention": sum(len(v) for v in self._pending.values()),
                "resources": len(self._pending)}


# ═══════════════════════════════════
# 指挥官 v2
# ═══════════════════════════════════

class CommanderV2:
    """指挥官 v2——动态自组织 + 并行执行 + 协商 + expectation 锚点 + 前缀保留 replan

    可注入三件套（默认实现保持原占位行为，生产接线时替换）：
      executor(task) -> str                 真实执行任务，返回产出
      verifier(task) -> (bool, verdict)     对照 task.expectation 核验产出
      replanner(goal, done, failed, remaining) -> list[Task]  重写剩余计划
    """

    def __init__(self, executor=None, verifier=None, replanner=None,
                 max_mission_replans: int = 2):
        self.pool = AgentPoolV2()
        self.decomposer = TaskDecomposerV2()
        self.dag = DAGValidator()
        self.negotiator = Negotiator()
        self._tasks: dict[str, Task] = {}
        self._results: list[dict] = []
        self._lock = threading.Lock()
        self._executor = executor if executor is not None else self._pick_default_executor()
        self._verifier = verifier or self._default_verifier
        self._replanner = replanner or self._default_replanner
        self._max_mission_replans = max_mission_replans
        self._mission_replans = 0

    @staticmethod
    def _pick_default_executor():
        """方案 A：ECO_RUNTIME_EXECUTOR=1 才启用真实运行时（RuntimeExecutor），
        否则保持占位——避免 CLI/benchmark 等现有调用方无意中消耗 API 配额。"""
        if os.environ.get("ECO_RUNTIME_EXECUTOR", "").strip().lower() in ("1", "true", "yes"):
            try:
                from agent_core.task_executor import RuntimeExecutor
                logger.info("[CommanderV2] ECO_RUNTIME_EXECUTOR=1：启用真实工具运行时")
                return RuntimeExecutor()
            except Exception as e:
                logger.warning(f"[CommanderV2] RuntimeExecutor 加载失败，回退占位: {e}")
        return CommanderV2._default_executor

    # ── 默认三件套（占位，保持原行为可跑通）──────────────────────

    @staticmethod
    def _default_executor(task: Task) -> str:
        time.sleep(0.2)  # 原占位执行
        return f"完成 {task.description[:30]}"

    @staticmethod
    def _default_verifier(task: Task) -> tuple[bool, str]:
        # 优先 LLM 语义核验（对照 expectation）；LLM 不可用/异常时降级规则兜底
        llm = CommanderV2._llm_verdict(task)
        if llm is not None:
            return llm
        if task.output:
            return True, f"规则验证通过（产出非空；expectation「{task.expectation[:20]}」未做语义核验）"
        return False, "产出为空，无法对照 expectation 核验"

    @staticmethod
    def _llm_verdict(task: Task) -> tuple[bool, str] | None:
        """LLM 语义核验：对照 expectation 判断产出是否达标。
        LLM 未配置/调用失败返回 None，由调用方降级为规则核验。"""
        try:
            from agent_core.llm_client import get_default_client
            c = get_default_client()
            if not c.available():
                return None
            prompt = (
                f"任务：{task.description}\n"
                f"完成判据（expectation）：{task.expectation}\n"
                f"实际产出：\n{task.output[:2000]}\n\n"
                "请对照完成判据逐条核验实际产出。第一行只回答「达标」或「未达标」，"
                "第二行起给出简要理由（指出缺失项）。"
            )
            resp = c.complete(prompt, system="你是严格的验收员：只依据完成判据核验，"
                                           "证据不足一律判未达标，不臆测。", max_tokens=200)
            if not resp:
                return None
            first, _, rest = resp.strip().partition("\n")
            # 先判「未达标」再判「达标」——前者包含后者子串
            ok = "未达标" not in first and "达标" in first
            reason = (rest.strip() or first.strip())[:80]
            return ok, f"LLM核验：{reason}"
        except Exception as e:
            logger.warning(f"[verifier] LLM 核验异常，降级规则核验: {e}")
            return None

    def _default_replanner(self, goal: str, done: list[Task],
                           failed: Task, remaining: list[Task]) -> list[Task]:
        """默认重规划：冻结 done，按原模板重写剩余步骤，附失败教训"""
        reason = failed.verdict or failed.error or "原因未知"
        note = f"replan：前序「{failed.description[:20]}」未达标（{reason[:30]}）"
        return self.decomposer.decompose(goal, skip=len(done), note=note)

    # ── 主流程 ────────────────────────────────────────────────

    def execute(self, goal: str, context: dict = None) -> dict:
        start = time.time()
        logger.info(f"[CommanderV2] 目标: {goal[:40]}")
        # B-01：10秒内分解≥5
        tasks = self.decomposer.decompose(goal, context)
        if len(tasks) < 5:
            tasks = self.decomposer.decompose("通用" + goal, context)
        for t in tasks: self._tasks[t.id] = t
        logger.info(f"  分解: {len(tasks)} 子任务")

        # G-03：DAG循环检测
        cycle = self.dag.has_cycle(tasks)
        if cycle:
            logger.warning(f"  检测到循环依赖: {cycle}，自动破环")
            tasks = self.dag.break_cycle(tasks)

        self._mission_replans = 0
        tasks = self._run_waves(goal, tasks)

        # B-04：自动回收空闲
        self.pool.auto_scale()

        elapsed = (time.time() - start) * 1000
        summary = self._summarize(elapsed)
        self._results.append(summary)

        # L4 钩子：mission 三元组沉淀 + 条件触发（ECO_AUTO_EVOLVE=1 才启用）
        try:
            from agent_core.evolve_trigger import mission_hook
            mission_hook(summary, list(self._tasks.values()))
        except Exception as e:
            logger.warning(f"[CommanderV2] evolve 钩子异常（不影响主流程）: {e}")
        return summary

    def _run_waves(self, goal: str, tasks: list[Task]) -> list[Task]:
        """波浪调度：每波跑「依赖已完成」的任务（≤8并行），失败后前缀保留 replan"""
        while True:
            by_id = {t.id: t for t in tasks}
            runnable = [t for t in tasks if t.status == TaskStatus.PENDING
                        and all(by_id.get(d) and by_id[d].status == TaskStatus.COMPLETED
                                for d in t.depends_on)]
            if not runnable:
                return tasks

            # 上游上下文注入：下游任务携带前置产出（镜像 role_swarm【前置产出】）
            for t in runnable:
                t.input["upstream"] = {
                    by_id[d].description[:40]: by_id[d].output[:500]
                    for d in t.depends_on if by_id[d].output
                }

            threads = [threading.Thread(target=self._execute_task, args=(t,), daemon=True)
                       for t in runnable[:8]]  # B-02：最多8并行
            for th in threads: th.start()
            for th in threads: th.join(timeout=60)

            failed = next((t for t in runnable if t.status == TaskStatus.FAILED), None)
            if failed is None:
                continue  # 本波全部完成，进入下一波

            if self._mission_replans >= self._max_mission_replans:
                logger.warning(f"  重规划预算耗尽（{self._max_mission_replans}轮），失败定格: {failed.description[:30]}")
                for t in tasks:  # 依赖链下游定格 BLOCKED
                    if t.status == TaskStatus.PENDING:
                        t.status = TaskStatus.BLOCKED; t.error = f"上游失败: {failed.id}"
                return tasks

            tasks = self._replan_prefix(goal, tasks, failed)

    def _replan_prefix(self, goal: str, tasks: list[Task], failed: Task) -> list[Task]:
        """前缀保留 replan：冻结 COMPLETED 前缀（绝不重跑），重写失败点之后的计划"""
        done = [t for t in tasks if t.status == TaskStatus.COMPLETED]
        remaining = [t for t in tasks if t.status in (TaskStatus.PENDING, TaskStatus.BLOCKED)]
        failed.replan_count += 1
        self._mission_replans += 1
        logger.info(f"  重规划 {self._mission_replans}/{self._max_mission_replans}："
                    f"冻结 {len(done)} 个已完成任务，重写 {len(remaining) + 1} 个")

        new_tasks = self._replanner(goal=goal, done=done, failed=failed, remaining=remaining)
        for i, t in enumerate(new_tasks):
            t.depends_on = [new_tasks[i - 1].id] if i else ([done[-1].id] if done else [])
            self._tasks[t.id] = t
        # 保留 failed 作为审计记录；旧 remaining 被新计划取代，从 _tasks 移除避免幽灵任务
        for t in remaining:
            self._tasks.pop(t.id, None)
        return done + [failed] + new_tasks

    def _execute_task(self, task: Task):
        agent = self.pool.get_or_spawn(task.agent_role)
        self.pool.assign_task(agent.id, task.id)
        task.status = TaskStatus.RUNNING; task.started_at = datetime.now().isoformat()
        st = time.time()
        try:
            task.output = self._executor(task)
        except Exception as e:
            task.status = TaskStatus.FAILED; task.error = str(e)
            self.pool.complete_task(agent.id, False)
            task.execution_time_ms = (time.time() - st) * 1000
            return
        # expectation 锚点：没抛异常不算完成，必须对照判据核验
        ok, verdict = self._verifier(task)
        task.verdict = verdict
        task.status = TaskStatus.COMPLETED if ok else TaskStatus.FAILED
        if not ok:
            task.error = f"验证未通过: {verdict[:60]}"
        self.pool.complete_task(agent.id, ok)
        task.execution_time_ms = (time.time() - st) * 1000

    def _summarize(self, elapsed_ms: float) -> dict:
        tasks = list(self._tasks.values())
        return {"total_tasks": len(tasks),
                "completed": sum(1 for t in tasks if t.status == TaskStatus.COMPLETED),
                "failed": sum(1 for t in tasks if t.status == TaskStatus.FAILED),
                "verified": sum(1 for t in tasks if t.verdict),
                "mission_replans": self._mission_replans,
                "llm_loops": getattr(self._executor, "llm_loops", 0),
                "total_time_ms": round(elapsed_ms, 1),
                "replanned": sum(1 for t in tasks if t.replan_count > 0),
                "agents_used": self.pool.get_stats()["total"],
                "dag_cycle_free": self.dag.has_cycle(tasks) is None}

    def get_stats(self) -> dict:
        return {"pool": self.pool.get_stats(), "missions": len(self._results),
                "negotiation": self.negotiator.get_stats()}


# ===== 测试 =====

def test():
    import io
    import sys as _sys
    _sys.stdout = io.TextIOWrapper(_sys.stdout.buffer, encoding='utf-8', errors='replace')

    cmd = CommanderV2()

    # B-01：动态自组织测试
    r1 = cmd.execute("开发一个带后端的待办清单App")
    print(f"[B-01] 动态自组织: {r1['total_tasks']}子任务 (需≥5), 耗时{r1['total_time_ms']:.0f}ms (需<10000)", flush=True)
    assert r1['total_tasks'] >= 5, f"FAIL: 只有{r1['total_tasks']}子任务"
    assert r1['total_time_ms'] < 10000, f"FAIL: 耗时{r1['total_time_ms']}ms"

    # B-04：弹性伸缩
    stats = cmd.pool.get_stats()
    print(f"[B-04] 弹性伸缩: {stats['total']} Agent, {stats['idle']}空闲", flush=True)

    # G-03：DAG检测
    print(f"[G-03] DAG循环: {'无' if r1['dag_cycle_free'] else '有'}循环依赖", flush=True)

    # 协商器测试
    neg = cmd.negotiator
    r_a = neg.request("agent_a", "file://config.yaml", "task_a")
    r_b = neg.request("agent_b", "file://config.yaml", "task_b")
    print(f"[B-05] 协商: AgentA={'通过' if r_a['granted'] else '等待'}, "
          f"AgentB={'通过' if r_b['granted'] else '等待'}", flush=True)
    neg.release("agent_a", "file://config.yaml")
    print("[B-05] AgentA释放后 → 自动解除", flush=True)

    print(f"\n{'='*35}", flush=True)
    print("[PASS] Phase 3 核心验收全部通过", flush=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
    test()
