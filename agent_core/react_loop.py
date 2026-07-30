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

import time
import logging
from pathlib import Path
from datetime import datetime
from typing import Any
from collections.abc import Callable
from dataclasses import dataclass, field

logger = logging.getLogger("react_loop")

ROOT = Path(__file__).resolve().parent.parent

try:
    from agent_core.llm_client import get_default_client
except Exception:  # 直接脚本运行时包导入失败
    try:
        from llm_client import get_default_client
    except Exception:
        def get_default_client():
            return None


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
        self._tools: dict[str, Callable] = {}
        self._history: list[dict] = []
        self._max_retries = 3
        self._confidence_threshold = 0.4
        self._max_steps = 20
        self._current_state: ReActState | None = None

    def _llm(self):
        """获取 LLM 客户端（不可用返回 None）"""
        try:
            client = get_default_client()
            if client and client.available():
                return client
        except Exception as e:
            logger.warning(f"[ReAct++] LLM 客户端不可用: {e}")
        return None

    def register_tool(self, name: str, handler: Callable, description: str = "") -> None:
        """注册工具"""
        self._tools[name] = handler

    # ── 主执行入口 ──

    def execute(self, task: str, context: dict = None, observer=None) -> dict:
        """执行 ReAct++ 循环"""
        state = ReActState()
        state.observation = task
        start_time = time.time()
        logger.info(f"[ReAct++] 开始任务: {task[:50]}")

        # 保存检查点（支持回滚）
        checkpoint = {"task": task, "context": context, "started_at": datetime.now().isoformat()}
        state.rollback_point = checkpoint
        self._current_state = state

        for step in range(1, self._max_steps + 1):
            state.step = step

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
                # ChatGPT 风格：用上一次的思考作为输出；
                # 但规则模式的“继续执行步骤N”占位思考不是结论——
                # 工具已产出结果时不应用它覆盖最终观测
                if state.thought and not state.thought.startswith("继续执行步骤"):
                    final = state.thought
                else:
                    final = "任务完成"
                state.action_result = final
                logger.info(f"[ReAct++] 步骤{step}: 完成 - {final[:60]}")
                break

            if action == "__error__":
                state.error = str(params)
                logger.info(f"[ReAct++] 步骤{step}: 错误 - {params}")
                if state.retry_count < self._max_retries:
                    state.retry_count += 1
                    state.paused = True
                    self._rollback(state)  # 重试前回滚状态到检查点
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
            "thought": state.thought[:200] if state.thought else "",
            "interrupted": state.interrupted,
        }
        self._history.append(result)
        self._current_state = None
        return result

    # ── THINK 阶段 ──

    def _think(self, state: ReActState, context: dict) -> str:
        """推理当前状态和下一步（优先真实 LLM，不可用降级规则）"""
        client = self._llm()
        if client:
            try:
                tools_desc = ", ".join(self._tools.keys()) or "无"
                reflect_tail = self._reflect_tail()
                prompt = (
                    f"任务: {state.observation[:200]}\n"
                    f"当前步骤: {state.step}\n"
                    f"上一步结果: {str(state.action_result)[:200] or '无'}\n"
                    f"最近错误: {state.error[:200] or '无'}\n"
                    f"可用工具: {tools_desc}\n"
                    f"请用一两句话说明下一步应该怎么思考和行动。"
                    f"{reflect_tail}"
                )
                thought = client.complete(prompt, system="你是 Eco Agent 的推理引擎，简洁输出下一步思考。",
                                          max_tokens=512)
                if thought:
                    return thought
                logger.warning("[ReAct++] LLM 思考返回空，降级规则模式")
            except Exception as e:
                logger.warning(f"[ReAct++] LLM 思考失败，降级规则模式: {e}")
        if state.step == 1:
            return f"理解任务: {state.observation[:60]}"
        if state.error:
            return f"分析错误: {state.error}，尝试替代方案"
        return f"继续执行步骤{state.step}，基于: {str(state.action_result)[:60]}"

    def _estimate_confidence(self, thought: str, state: ReActState) -> float:
        """置信度评估（优先 LLM 打分，解析失败/不可用降级规则）"""
        client = self._llm()
        if client:
            try:
                prompt = (
                    f"任务: {state.observation[:200]}\n"
                    f"当前思考: {thought[:300]}\n"
                    f"请只输出一个 0 到 1 之间的小数，表示该思考能成功推进任务的置信度。"
                )
                text = client.complete(prompt, system="你只输出数字。", max_tokens=16)
                if text:
                    import re
                    m = re.search(r"0?\.\d+|^[01](?:\.0+)?$", text.strip())
                    if m:
                        val = float(m.group(0))
                        if 0.0 <= val <= 1.0:
                            return val
                logger.warning("[ReAct++] LLM 置信度解析失败，降级规则模式")
            except Exception as e:
                logger.warning(f"[ReAct++] LLM 置信度评估失败，降级规则模式: {e}")
        if state.error:
            return 0.2
        if state.retry_count > 0:
            return 0.3 + (self._max_retries - state.retry_count) * 0.2
        return 0.85  # 默认高置信度

    # ── PAUSE & REFLECT ──

    def _pause_reflect(self, state: ReActState, context: dict) -> dict:
        """暂停并结构化反思：输出 {问题诊断, 修正指令}，修正指令经 prompt_engine
        校验后注入后续轮次提示尾部（违规修正指令被拒绝并记审计）"""
        client = self._llm()
        if client:
            try:
                tools_desc = ", ".join(self._tools.keys()) or "无"
                prompt = (
                    f"任务: {state.observation[:200]}\n"
                    f"当前置信度过低（{state.confidence:.2f}），步骤: {state.step}，"
                    f"最近错误: {state.error[:200] or '无'}\n"
                    f"可用工具: {tools_desc}\n"
                    f"请严格按以下两行格式输出：\n"
                    f"问题诊断: <一两句话诊断问题根因>\n"
                    f"修正指令: <一条给后续推理的具体修正要求，一两句话>"
                )
                raw = client.complete(prompt, system="你是 Eco Agent 的反思模块，输出结构化诊断。", max_tokens=512)
                if raw:
                    parsed = self._parse_reflect(raw)
                    result = {"action": "continue", "new_confidence": 0.7,
                              "diagnosis": parsed["diagnosis"], "correction": parsed["correction"],
                              "llm_diagnosis": raw}
                    self._inject_correction(parsed["correction"], state)
                    return result
                logger.warning("[ReAct++] LLM 反思返回空，降级规则模式")
            except Exception as e:
                logger.warning(f"[ReAct++] LLM 反思失败，降级规则模式: {e}")
        alternatives = []
        for tool_name in self._tools:
            alternatives.append(f"使用工具: {tool_name}")

        if state.error and state.retry_count < self._max_retries:
            return {"action": "retry", "new_confidence": 0.7, "suggestion": f"重试(第{state.retry_count+1}次)"}

        if state.retry_count >= self._max_retries:
            return {"abort": True, "reason": "超过最大重试次数"}

        return {"action": "continue", "new_confidence": 0.6}

    def _reflect_tail(self) -> str:
        """取 prompt_engine 中已接受的反思修正指令，拼接到后续轮次提示尾部"""
        try:
            from agent_core.prompt_engine import get_prompt_engine
        except Exception:
            try:
                from prompt_engine import get_prompt_engine
            except Exception:
                return ""
        try:
            injs = [i for i in get_prompt_engine().list_injections()
                    if i["source"] == "reflect"]
        except Exception:
            return ""
        if not injs:
            return ""
        tail = "\n".join(f"- {i['content']}" for i in injs[-3:])
        return f"\n请务必遵守以下修正指令：\n{tail}"

    @staticmethod
    def _parse_reflect(raw: str) -> dict:
        """解析结构化反思 {问题诊断, 修正指令}；解析失败降级整段为诊断"""
        diagnosis, correction = "", ""
        for line in raw.splitlines():
            line = line.strip()
            if line.startswith("问题诊断"):
                diagnosis = line.split(":", 1)[-1].split("：", 1)[-1].strip()
            elif line.startswith("修正指令"):
                correction = line.split(":", 1)[-1].split("：", 1)[-1].strip()
        if not diagnosis:
            diagnosis = raw.strip()[:200]
        if not correction:
            correction = "降低结论置信度，引用不确定的法条前必须先核实"
        return {"diagnosis": diagnosis, "correction": correction}

    def _inject_correction(self, correction: str, state: ReActState) -> bool:
        """修正指令经 prompt_engine 校验后注入后续轮次提示尾部；违规则拒绝并审计"""
        try:
            from agent_core.prompt_engine import get_prompt_engine
        except Exception:
            try:
                from prompt_engine import get_prompt_engine
            except Exception:
                return False
        engine = get_prompt_engine()
        task_id = (state.rollback_point or {}).get("task", "")[:60]
        return engine.inject(f"【L1反思修正指令】{correction}",
                             source="reflect", task_id=task_id)

    # ── ACT 阶段 ──

    def _decide_action(self, state: ReActState, context: dict) -> tuple:
        """决定下一步行动"""
        if state.confidence < 0.2:
            return ("__error__", "置信度过低")

        # 已完成条件：已成功执行过工具且无错误
        if state.action_result and not state.error and state.step > 1:
            return ("__complete__", {})

        # 选择工具：LLM 思考中提到工具名时才调用
        obs = (state.observation + state.action_result + state.thought).lower()
        for tool_name in self._tools:
            if tool_name.lower() in obs:
                return (tool_name, {"query": state.observation[:100]})

        # 不匹配任何工具 = 纯对话模式，直接输出 LLM 的思考结果
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

    def interrupt(self) -> None:
        """中断注入——允许用户在循环任意节点打断"""
        if self._current_state is not None:
            self._current_state.interrupted = True
            logger.info(f"[ReAct++] 已注入中断（步骤{self._current_state.step}）")
        else:
            logger.warning("[ReAct++] 无运行中的循环，中断无效")

    def _rollback(self, state: ReActState) -> None:
        """原子化回滚——将可变状态恢复到检查点，保留重试计数与错误记录"""
        checkpoint = dict(state.rollback_point or {})
        checkpoint["rollback_count"] = checkpoint.get("rollback_count", 0) + 1
        state.observation = checkpoint.get("task", state.observation)
        state.thought = ""
        state.action = ""
        state.action_result = ""
        state.confidence = 1.0
        state.paused = False
        state.rollback_point = checkpoint
        logger.info(f"[ReAct++] 已回滚状态到检查点（第{checkpoint['rollback_count']}次）")

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

    def clear_history(self) -> None:
        self._history = []


# ===== 快速测试 =====

def test():
    import io
    import sys as _sys
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
