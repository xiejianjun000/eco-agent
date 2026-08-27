"""
checkpoint_policy.py — fail-closed 检查点策略（对标 DSH checkpoint policy）

DSH 语义：LLM 请求前 / 工具执行前必须 flush 会话状态，失败 fail-closed。
本实现：高风险事件类型执行前，会话日志必须处于可验证的持久完整状态；
发现断尾自动修复，修复后仍不完整则抛 SessionDurabilityError 阻断执行。
"""

from __future__ import annotations

from agent_core.session_log import SessionEventLog

# 需要持久性前置校验的高风险事件（执行前 guard）
REQUIRES_DURABLE: tuple[str, ...] = (
    "llm/request",
    "tool/call",
    "tool/result",
    "user/message",
)


class SessionDurabilityError(RuntimeError):
    """fail-closed：会话日志未达持久完整状态，拒绝执行高风险操作。"""


def requires_durable(event_type: str) -> bool:
    """该事件类型是否要求持久性前置校验。"""
    return event_type in REQUIRES_DURABLE


def durable_guard(slog: SessionEventLog, event_type: str) -> None:
    """高风险操作前的持久性守卫：
    1. 不需要校验的事件直接放行；
    2. 链完整 → 放行；
    3. 断尾 → 自动修复后再查；
    4. 仍不完整（中部损坏等）→ 抛错 fail-closed。"""
    if not requires_durable(event_type):
        return
    ok, report = slog.durable()
    if ok:
        return
    repaired = slog.repair_torn_tail()
    if not repaired.get("repaired"):
        repaired = slog.repair_seq_gap()
    ok2, report2 = slog.durable()
    if not ok2:
        raise SessionDurabilityError(
            f"会话日志持久性校验失败: {report2} (repair={repaired})")
