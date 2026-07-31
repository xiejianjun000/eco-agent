"""
审批工作流模块 — 多级审批链、超时自动拒绝、审计记录关联。

设计原则:
- 多级审批链：按 approvers 顺序逐级审批
- 超时控制：全局超时，到期后根据 auto_approve_on_timeout 决定行为
- 审计关联：可关联 AuditChain 实例，审批动作自动写入审计记录
- 不可逆：approve/reject/skip 均为单向操作，已完成的步骤不可回退
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class ApprovalStatus(Enum):
    """审批状态枚举"""

    PENDING = "pending"  # 待审批
    APPROVED = "approved"  # 已通过
    REJECTED = "rejected"  # 已拒绝
    TIMEOUT = "timeout"  # 超时（根据配置可视为拒绝或通过）
    SKIPPED = "skipped"  # 已跳过（该级审批人不可用时）


@dataclass
class ApprovalStep:
    """单个审批步骤的数据记录"""

    level: int  # 审批级别 (1-based)
    approver: str  # 审批人标识
    status: ApprovalStatus = ApprovalStatus.PENDING
    timestamp: float = 0.0  # 操作时间戳 (Unix timestamp)
    comment: str = ""  # 审批备注

    def to_dict(self) -> dict:
        """序列化为字典"""
        return {
            "level": self.level,
            "approver": self.approver,
            "status": self.status.value,
            "timestamp": self.timestamp,
            "comment": self.comment,
        }


class ApprovalFlow:
    """
    多级审批工作流。

    按 approvers 列表顺序逐级审批。支持全局超时控制，
    超时后根据 auto_approve_on_timeout 标志自动通过或拒绝。

    可选关联 AuditChain 实例，审批动作自动追加审计记录。

    Usage:
        # 两级审批，5分钟超时
        flow = ApprovalFlow(["dept_head", "director"], timeout=300)

        # 第一级审批通过
        status = flow.approve("dept_head", "同意")
        assert status == ApprovalStatus.APPROVED

        # 第二级审批通过
        status = flow.approve("director")
        assert flow.is_approved()

        # 结果
        print(flow.result())        # ApprovalStatus.APPROVED
        print(flow.to_dict_list())  # 可序列化列表
    """

    def __init__(
        self,
        approvers: list[str],
        timeout: float = 300,
        auto_approve_on_timeout: bool = False,
        audit_chain=None,
    ):
        """
        初始化审批流。

        Args:
            approvers: 审批人列表，按审批顺序排列
            timeout: 全局超时时间（秒），从构造时刻开始计时
            auto_approve_on_timeout: True=超时自动通过, False=超时自动拒绝
            audit_chain: 可选 AuditChain 实例，用于自动记录审批动作
        """
        if not approvers:
            raise ValueError("approvers 列表不能为空")

        self._approvers = list(approvers)
        self.timeout = float(timeout)
        self.auto_approve_on_timeout = bool(auto_approve_on_timeout)
        self._audit_chain = audit_chain

        # 初始化审批步骤
        self.steps: list[ApprovalStep] = [
            ApprovalStep(level=i + 1, approver=name) for i, name in enumerate(approvers)
        ]

        self.current_level: int = 1  # 当前待审批级别 (1-based)
        self._start_time: float = time.time()
        self._completed: bool = False

    # ── 私有方法 ──────────────────────────────────────────

    def _elapsed(self) -> float:
        """已流逝时间（秒）"""
        return time.time() - self._start_time

    def _is_timed_out(self) -> bool:
        """检查是否已超时"""
        return self._elapsed() > self.timeout

    def _current_step(self) -> ApprovalStep | None:
        """获取当前待审批的步骤，若已完成则返回 None"""
        if self._completed or self.current_level > len(self.steps):
            return None
        return self.steps[self.current_level - 1]

    def _handle_timeout(self) -> ApprovalStatus | None:
        """
        处理超时情况。

        若未超时或已无待审批步骤，返回 None。
        若超时：
          - auto_approve_on_timeout=True  → 标记当前步骤为 APPROVED
          - auto_approve_on_timeout=False → 标记当前步骤为 TIMEOUT
        返回应用的状态。
        """
        if not self._is_timed_out():
            return None

        step = self._current_step()
        if step is None:
            return None

        if self.auto_approve_on_timeout:
            step.status = ApprovalStatus.APPROVED
            step.timestamp = time.time()
            step.comment = step.comment or "超时自动通过"
        else:
            step.status = ApprovalStatus.TIMEOUT
            step.timestamp = time.time()
            step.comment = step.comment or "超时自动拒绝"

        self._finalize_step(step)
        return step.status

    def _finalize_step(self, step: ApprovalStep) -> None:
        """
        完成当前步骤：推进 current_level，检查是否全部完成。

        若审批被拒绝或超时（且非自动通过），整个流程终止。
        """
        if step.status in (ApprovalStatus.REJECTED, ApprovalStatus.TIMEOUT):
            # 终止流程 — 标记所有后续步骤为 SKIPPED
            for remaining in self.steps[self.current_level :]:
                remaining.status = ApprovalStatus.SKIPPED
                remaining.timestamp = time.time()
                remaining.comment = remaining.comment or "前置审批未通过，自动跳过"
            self._completed = True
        else:
            self.current_level += 1
            if self.current_level > len(self.steps):
                self._completed = True

    def _record_audit(self, step: ApprovalStep) -> None:
        """向关联的审计链追加记录"""
        if self._audit_chain is None:
            return
        try:
            comment_bytes = step.comment.encode("utf-8")
            self._audit_chain.add_entry(
                operation="approval_step",
                operator=step.approver,
                input_data=f"level={step.level}".encode(),
                output_data=comment_bytes,
                approval_status=step.status.value,
            )
        except Exception:
            pass  # 审计记录失败不应阻断审批流程

    # ── 公共方法 ──────────────────────────────────────────

    def approve(self, approver: str, comment: str = "") -> ApprovalStatus:
        """
        当前级别审批通过。

        Args:
            approver: 审批人标识，必须匹配当前级别的审批人
            comment: 审批备注

        Returns:
            当前步骤的最终状态

        Raises:
            ValueError: 审批人不匹配当前级别
        """
        # 先检查超时
        timeout_result = self._handle_timeout()
        if timeout_result is not None:
            return timeout_result

        step = self._current_step()
        if step is None:
            return self.result()

        if approver != step.approver:
            raise ValueError(
                f"审批人不匹配: 当前级别({step.level})需要 '{step.approver}'，但收到 '{approver}'"
            )

        step.status = ApprovalStatus.APPROVED
        step.timestamp = time.time()
        step.comment = comment

        self._record_audit(step)
        self._finalize_step(step)
        return ApprovalStatus.APPROVED

    def reject(self, approver: str, comment: str = "") -> ApprovalStatus:
        """
        当前级别审批拒绝。

        Args:
            approver: 审批人标识，必须匹配当前级别的审批人
            comment: 拒绝原因

        Returns:
            当前步骤的最终状态
        """
        # 先检查超时
        timeout_result = self._handle_timeout()
        if timeout_result is not None:
            return timeout_result

        step = self._current_step()
        if step is None:
            return self.result()

        if approver != step.approver:
            raise ValueError(
                f"审批人不匹配: 当前级别({step.level})需要 '{step.approver}'，但收到 '{approver}'"
            )

        step.status = ApprovalStatus.REJECTED
        step.timestamp = time.time()
        step.comment = comment

        self._record_audit(step)
        self._finalize_step(step)
        return ApprovalStatus.REJECTED

    def skip(self, comment: str = "") -> ApprovalStatus:
        """
        跳过当前审批级别。

        用于审批人不可用（请假、调岗等）时的应急处理。
        跳过后推进到下一级别继续审批。

        Args:
            comment: 跳过原因

        Returns:
            当前步骤的最终状态
        """
        # 先检查超时
        timeout_result = self._handle_timeout()
        if timeout_result is not None:
            return timeout_result

        step = self._current_step()
        if step is None:
            return self.result()

        step.status = ApprovalStatus.SKIPPED
        step.timestamp = time.time()
        step.comment = comment or "审批人跳过"

        self._record_audit(step)
        # skip 后继续推进（不终止流程）
        self.current_level += 1
        if self.current_level > len(self.steps):
            self._completed = True
        return ApprovalStatus.SKIPPED

    def is_complete(self) -> bool:
        """
        审批流程是否已完成（无论通过与否）。

        Returns:
            True 如果所有审批步骤均已处理或流程已终止
        """
        if self._completed:
            return True
        # 兜底检查超时
        self._handle_timeout()
        return self._completed

    def is_approved(self) -> bool:
        """
        审批是否全部通过。

        Returns:
            True 如果所有级别均已通过（包括超时自动通过）
        """
        if not self.is_complete():
            return False
        return all(
            s.status in (ApprovalStatus.APPROVED, ApprovalStatus.SKIPPED) for s in self.steps
        )

    def result(self) -> ApprovalStatus:
        """
        获取审批流程的最终状态。

        - 全部通过 → APPROVED
        - 被拒绝（含超时拒绝） → REJECTED
        - 尚未完成 → PENDING

        Returns:
            流程最终状态
        """
        self._handle_timeout()
        if not self._completed:
            return ApprovalStatus.PENDING
        if self.is_approved():
            return ApprovalStatus.APPROVED
        # 检查是否有被拒绝或超时的步骤
        for s in self.steps:
            if s.status == ApprovalStatus.REJECTED:
                return ApprovalStatus.REJECTED
            if s.status == ApprovalStatus.TIMEOUT:
                return ApprovalStatus.TIMEOUT
        return ApprovalStatus.REJECTED

    def to_dict_list(self) -> list[dict]:
        """
        将所有审批步骤序列化为字典列表。

        Returns:
            审批步骤列表，每个元素为一个 dict
        """
        self._handle_timeout()
        return [step.to_dict() for step in self.steps]

    def __repr__(self) -> str:
        status = "completed" if self._completed else "in_progress"
        return (
            f"<ApprovalFlow level={self.current_level}/{len(self.steps)}"
            f" status={status} elapsed={self._elapsed():.1f}s>"
        )


# ── 便捷工厂函数 ──────────────────────────────────────────


def create_single_approval(approver: str, timeout: float = 300) -> ApprovalFlow:
    """
    创建单级审批流。

    Args:
        approver: 审批人标识
        timeout: 超时时间（秒）

    Returns:
        配置好的 ApprovalFlow 实例
    """
    return ApprovalFlow(approvers=[approver], timeout=timeout)


def create_multi_approval(approvers: list[str], timeout: float = 300) -> ApprovalFlow:
    """
    创建多级审批流。

    Args:
        approvers: 审批人列表（按审批顺序）
        timeout: 超时时间（秒）

    Returns:
        配置好的 ApprovalFlow 实例
    """
    return ApprovalFlow(approvers=approvers, timeout=timeout)
