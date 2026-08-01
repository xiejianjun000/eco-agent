#!/usr/bin/env python3
"""
task_executor.py — L2 子任务真实执行器（RuntimeExecutor）

把 CommanderV2 的占位 executor 接到真实运行时：
  每个 L2 Task → 起一个 L1 ReAct++ 循环（think→act→observe，置信度门控），
  工具从 tools_registry 桥接注入（async execute_tool → 同步 wrapper，
  权限闸门 L1-L4 在 execute_tool 内部生效，全程 SM3 审计）。

启用方式（方案 A——显式启用，默认占位不烧配额）：
  CommanderV2(executor=RuntimeExecutor())  或  ECO_RUNTIME_EXECUTOR=1

降级红线：LLM 未配置/不可用时静默回退占位行为（离线测试安全）。
"""

import asyncio
import logging
import time

logger = logging.getLogger("task_executor")

# L2 子任务粒度的 ReAct 循环步数上限（L1 默认 20 步对子任务过重）
DEFAULT_MAX_STEPS = 5


def _run_async(coro):
    """在任意线程安全地执行协程：独立事件循环，用完即关。
    execute_tool 是 async；L2 工作线程内没有运行中的 loop，新建最稳。"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class RuntimeExecutor:
    """L2 真实执行器：Task → ReAct++ + tools_registry 工具集 → 真实产出

    统计 llm_loops（实际起的 LLM 循环数），供 CommanderV2._summarize 上报。
    """

    def __init__(self, max_steps: int = DEFAULT_MAX_STEPS):
        self._max_steps = max_steps
        self.llm_loops = 0

    def __call__(self, task) -> str:
        client = self._get_client()
        if client is None:
            return self._placeholder(task)
        return self._run_react(task)

    # ── 降级路径 ──────────────────────────────────────────────

    @staticmethod
    def _get_client():
        try:
            from agent_core.llm_client import get_default_client
            c = get_default_client()
            if c and c.available():
                return c
        except Exception as e:
            logger.warning(f"[RuntimeExecutor] LLM 客户端获取失败，降级占位: {e}")
        return None

    @staticmethod
    def _placeholder(task) -> str:
        time.sleep(0.2)  # 与原占位行为一致（离线/测试安全）
        return f"完成 {task.description[:30]}"

    # ── 真实路径 ──────────────────────────────────────────────

    def _run_react(self, task) -> str:
        from agent_core.react_loop import ReActPlusPlus
        loop = ReActPlusPlus()
        loop._max_steps = self._max_steps
        self._register_tools(loop, role=task.agent_role.value)

        prompt = self._build_prompt(task)
        result = loop.execute(prompt, context={"task_id": task.id,
                                               "role": task.agent_role.value,
                                               "expectation": task.expectation})
        self.llm_loops += 1

        final = (result.get("final_observation") or "").strip()
        if not final:
            # 抛异常走 L2 replan 路径（与验证失败统一失败语义）
            raise RuntimeError(f"ReAct 循环无产出（{result.get('steps', 0)}步）: {task.description[:30]}")
        return final

    @staticmethod
    def _build_prompt(task) -> str:
        """任务 prompt = 描述 + expectation 判据 + 【前置产出】（镜像 role_swarm 拼法）"""
        parts = [task.description]
        if task.expectation:
            parts.append(f"\n【完成判据】\n{task.expectation}")
        upstream = (task.input or {}).get("upstream") or {}
        if upstream:
            ctx = "\n".join(f"· {k}: {str(v)[:500]}" for k, v in upstream.items())
            parts.append(f"\n【前置产出】\n{ctx}")
        return "".join(parts)

    # 分析/规划/写作/审查/研究类角色：只给只读（L1）工具。
    # 纯分析任务塞全量工具会诱导 LLM 不思考反而乱调工具（冒烟实测缺陷3）
    _READONLY_ROLES = frozenset({"analyst", "planner", "writer", "reviewer", "researcher"})

    def _register_tools(self, loop, role: str = "") -> int:
        """tools_registry 工具注入 ReAct 循环（同步 wrapper 桥接 async execute_tool，
        并携带 parameters schema 供 LLM 结构化决策）。
        角色感知过滤：分析类角色只注册 L1 只读工具，执行类角色给全量。
        权限闸门（L1-L4）在 execute_tool 内部统一生效，本层不重复设卡。"""
        try:
            from agent_core.tools_registry import get_tools, execute_tool
        except Exception as e:
            logger.warning(f"[RuntimeExecutor] tools_registry 不可用，无工具运行: {e}")
            return 0

        readonly = role in self._READONLY_ROLES
        risk_level = None
        if readonly:
            try:
                from agent_core.permissions import tool_risk_level
                risk_level = tool_risk_level
            except Exception:
                risk_level = None  # 权限模块缺席时退化为全量（闸门仍在 execute_tool 内）

        def _make_sync(name):
            def _handler(**kwargs):
                return _run_async(execute_tool(name, kwargs))
            return _handler

        count = 0
        for t in get_tools():
            fn = t.get("function", {})
            name = fn.get("name", "")
            if not name:
                continue
            if readonly and risk_level is not None and risk_level(name) != "L1":
                continue
            loop.register_tool(name, _make_sync(name),
                               description=fn.get("description", ""),
                               schema=fn.get("parameters") or {})
            count += 1
        logger.info(f"[RuntimeExecutor] 注入 {count} 个工具（role={role or 'default'}"
                    f"{'，只读过滤' if readonly else ''}）")
        return count
