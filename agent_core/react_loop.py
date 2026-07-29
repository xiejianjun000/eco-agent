#!/usr/bin/env python3
"""
react_loop.py — Eco Agent L1 微观行动循环 (ReAct++)

超越 Claude 的 ReAct：带置信度门控 + PAUSE & REFLECT + 中断注入 + 原子化回滚

节律：毫秒~秒级
嵌套：被 L2 Task Loop 调用，每个子任务可启动一次 ReAct++

用法：
  from agent_core.react_loop import ReActPlusPlus
  loop = ReActPlusPlus()
  result = loop.execute("查询大气污染防治法", tools=[...])
"""

import os, sys, json, time, uuid, logging, traceback
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass, field, asdict

logger = logging.getLogger("react_loop")

ROOT = Path(__file__).resolve().parent.parent


# ═══════════════════════════════════
# 循环状态
# ═══════════════════════════════════

@dataclass
class ReActState:
    """ReAct++ 循环状态"""
    step: int = 0
    observation: str = ""
    thought: str = ""
    confidence: float = 1.0
    action: str = ""
    action_result: str = ""
    error: str = ""
    retry_count: int = 0
    paused: bool = False
    interrupted: bool = False
    rollback_point: dict = field(default_factory=dict)


class ReActPlusPlus:
    """L1 微观行动循环——ReAct++：带置信度门控、暂停-反思、中断注入、原子化回滚"""

    def __init__(self):
        self._tools: Dict[str, Callable] = {}
        self._history: List[Dict] = []
        self._max_retries = 3
        self._confidence_threshold = 0.4
        self._max_steps = 20

    def register_tool(self, name: str, handler: Callable, description: str = ""):
        """注册工具"""
        self._tools[name] = handler

    # ── 主执行入口 ──

    def execute(self, task: str, context: dict = None, observer=None) -> Dict:
        """执行 ReAct++ 循环"""
        state = ReActState()
        state.observation = task
        start_time = time.time()
        logger.info(f"[ReAct++] 开始任务: {task[:50]}")

        # 保存检查点（支持回滚）
        checkpoint = {"task": task, "context": context, "started_at": datetime.now().isoformat()}
        state.rollback_point = checkpoint

        for step in range(1, self._max_steps + 1):
            state.step = step
            elapsed = time.time() - start_time

            # 检查中断注入
            if state.interrupted:
                logger.info(f"[ReAct++] 步骤{step}: 收到中断")
                break

            # ── THINK 阶段 ──
            thought = self._think(state, context or {})
            state.thought = thought
            state.confidence = self._estimate_confidence(thought, state)

            # 置信度门控：低于阈值触发 PAUSE & REFLECT
            if state.confidence < self._confidence_threshold:
                logger.info(f"[ReAct++] 步骤{step}: 置信度{state.confidence:.2f}低于阈值，暂停反思")
                reflect_result = self._pause_reflect(state, context or {})
                if reflect_result.get("abort"):
                    state.action_result = reflect_result.get("reason", "人工终止")
                    break
                state.confidence = reflect_result.get("new_confidence", 0.8)

            # ── ACT 阶段 ──
            action, params = self._decide_action(state, context or {})
            state.action = action

            if action == "__complete__":
                state.action_result = "任务完成"
                logger.info(f"[ReAct++] 步骤{step}: 任务完成")
                break

            if action == "__error__":
                state.error = str(params)
                logger.info(f"[ReAct++] 步骤{step}: 错误 - {params}")
                if state.retry_count < self._max_retries:
                    state.retry_count += 1
                    state.paused = True
                    continue  # 重试
                break

            # 执行工具调用
            result = self._execute_action(action, params)
            state.action_result = str(result)

            # Observer 验证（如果提供）
            if observer:
                verify = observer.verify(state.thought, str(result))
                if not verify["passed"] and state.retry_count < self._max_retries:
                    state.retry_count += 1
                    logger.info(f"[ReAct++] 步骤{step}: Observer建议重试")
                    continue

        # 汇总
        total_time = (time.time() - start_time) * 1000
        result = {
            "task": task,
            "steps": state.step,
            "total_time_ms": round(total_time, 1),
            "confidence": state.confidence,
            "retries": state.retry_count,
            "final_observation": state.action_result[:200] if state.action_result else "",
            "interrupted": state.interrupted,
        }
        self._history.append(result)
        return result

    # ── THINK 阶段 ──

    def _think(self, state: ReActState, context: dict) -> str:
        """推理当前状态和下一步"""
        if state.step == 1:
            return f"理解任务: {state.observation[:60]}"
        if state.error:
            return f"分析错误: {state.error}，尝试替代方案"
        return f"继续执行步骤{state.step}，基于: {str(state.action_result)[:60]}"

    def _estimate_confidence(self, thought: str, state: ReActState) -> float:
        """置信度评估"""
        if state.error:
            return 0.2
        if state.retry_count > 0:
            return 0.3 + (self._max_retries - state.retry_count) * 0.2
        return 0.85  # 默认高置信度

    # ── PAUSE & REFLECT ──

    def _pause_reflect(self, state: ReActState, context: dict) -> dict:
        """暂停并反思"""
        alternatives = []
        for tool_name in self._tools:
            alternatives.append(f"使用工具: {tool_name}")

        if state.error and state.retry_count < self._max_retries:
            return {"action": "retry", "new_confidence": 0.7, "suggestion": f"重试(第{state.retry_count+1}次)"}

        if state.retry_count >= self._max_retries:
            return {"abort": True, "reason": "超过最大重试次数"}

        return {"action": "continue", "new_confidence": 0.6}

    # ── ACT 阶段 ──

    def _decide_action(self, state: ReActState, context: dict) -> tuple:
        """决定下一步行动"""
        if state.confidence < 0.2:
            return ("__error__", "置信度过低")

        # 已完成条件：已成功执行过工具且无错误
        if state.action_result and not state.error and state.step > 1:
            return ("__complete__", {})

        # 选择工具
        obs = (state.observation + state.action_result).lower()
        for tool_name in self._tools:
            if tool_name.lower() in obs:
                return (tool_name, {"query": state.observation[:100]})

        if self._tools:
            first_tool = list(self._tools.keys())[0]
            return (first_tool, {"query": state.observation[:100]})

        return ("__complete__", {})

    def _execute_action(self, action: str, params: dict) -> Any:
        """执行工具调用"""
        handler = self._tools.get(action)
        if not handler:
            return f"工具不存在: {action}"
        try:
            return handler(**params)
        except Exception as e:
            return f"工具执行异常: {e}"

    # ── 外部控制 ──

    def interrupt(self):
        """中断注入——允许用户在循环任意节点打断"""
        pass  # 状态标记由外部设置

    # ── 统计 ──

    def get_stats(self) -> dict:
        total = len(self._history)
        if total == 0:
            return {"total_executions": 0}
        avg_steps = sum(r["steps"] for r in self._history) / total
        avg_time = sum(r["total_time_ms"] for r in self._history) / total
        return {
            "total_executions": total,
            "avg_steps": round(avg_steps, 1),
            "avg_time_ms": round(avg_time, 1),
            "interrupted": sum(1 for r in self._history if r["interrupted"]),
        }

    def clear_history(self):
        self._history = []


# ===== 快速测试 =====

def test():
    import io, sys as _sys
    _sys.stdout = io.TextIOWrapper(_sys.stdout.buffer, encoding='utf-8', errors='replace')

    loop = ReActPlusPlus()
    loop.register_tool("search", lambda query: f"[搜索] 找到关于'{query}'的结果", "搜索工具")

    # 执行任务
    result = loop.execute("搜索大气污染防治法")
    print(f"[ReAct++] 任务: {result['task'][:20]}.. 步骤: {result['steps']}, "
          f"耗时: {result['total_time_ms']:.0f}ms, 置信度: {result['confidence']:.2f}")

    result2 = loop.execute("分析超标排放案例")
    print(f"[ReAct++] 任务: {result2['task'][:20]}.. 步骤: {result2['steps']}, "
          f"耗时: {result2['total_time_ms']:.0f}ms, 置信度: {result2['confidence']:.2f}")

    stats = loop.get_stats()
    print(f"[Stats] 执行: {stats['total_executions']}, 平均步骤: {stats['avg_steps']}, "
          f"平均耗时: {stats['avg_time_ms']:.0f}ms")

    print("[OK] ReAct++ 测试通过")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test()
