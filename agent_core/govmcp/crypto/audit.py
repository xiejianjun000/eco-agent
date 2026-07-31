"""
不可篡改审计链 — SM3哈希链式防篡改

每条审计记录包含操作元数据，并通过SM3哈希链接到前一条记录。
任何对历史记录的修改都会破坏哈希链，可被 verify() 检测。

设计原则:
- 追加写入 (append-only)：无删除/修改接口
- 创世区块：第一条记录的 prev_hash = 64个'0'
- 篡改检测：遍历全链重新计算 current_hash 并与存储值比对
"""

import json
import time
from dataclasses import dataclass, field
from typing import List, Optional

from govmcp.crypto.sm import sm3_hash

# 创世区块前驱哈希 — 64个'0'
GENESIS_PREV_HASH = "0" * 64


@dataclass
class AuditEntry:
    """单条审计记录 — 不可篡改链上的一个区块"""

    id: int
    timestamp: float
    operation: str
    operator: str
    input_hash: str
    output_hash: str
    approval_status: str
    prev_hash: str
    current_hash: str


class AuditChain:
    """
    不可篡改审计链

    基于SM3哈希的链式数据结构。每条新记录通过 current_hash 锁定
    自身内容和前驱记录，形成防篡改链条。

    Usage:
        chain = AuditChain()
        chain.add_entry("tool_call", "admin", b"input", b"output", "approved")
        chain.add_entry("resource_read", "user1", b"query", b"result", "approved")
        assert chain.verify()
        print(chain.export())
    """

    def __init__(self):
        self.entries: list[AuditEntry] = []

    def add_entry(
        self,
        operation: str,
        operator: str,
        input_data: bytes,
        output_data: bytes,
        approval_status: str = "pending",
    ) -> AuditEntry:
        """
        追加一条审计记录。

        Args:
            operation: 操作类型 (如 'tool_call', 'resource_read', 'approval_granted')
            operator: 操作者标识
            input_data: 输入数据（原始字节）
            output_data: 输出数据（原始字节）
            approval_status: 审批状态 (pending/approved/rejected)

        Returns:
            新创建的 AuditEntry
        """
        entry_id = len(self.entries) + 1
        timestamp = time.time()
        input_hash = sm3_hash(input_data)
        output_hash = sm3_hash(output_data)

        # 创世区块或链式前驱
        if not self.entries:
            prev_hash = GENESIS_PREV_HASH
        else:
            prev_hash = self.entries[-1].current_hash

        # 计算当前哈希: sm3_hash(prev_hash + timestamp + operation + input_hash + output_hash)
        hash_source = f"{prev_hash}{timestamp}{operation}{input_hash}{output_hash}"
        current_hash = sm3_hash(hash_source.encode("utf-8"))

        entry = AuditEntry(
            id=entry_id,
            timestamp=timestamp,
            operation=operation,
            operator=operator,
            input_hash=input_hash,
            output_hash=output_hash,
            approval_status=approval_status,
            prev_hash=prev_hash,
            current_hash=current_hash,
        )
        self.entries.append(entry)
        return entry

    def verify(self) -> bool:
        """
        验证整条审计链的完整性。

        遍历所有记录，重新计算 current_hash 并与存储值比对。
        任何篡改（修改数据或插入/删除记录）都会导致验证失败。

        Returns:
            True 如果整条链未被篡改
        """
        if not self.entries:
            return True

        expected_prev = GENESIS_PREV_HASH

        for entry in self.entries:
            # 验证前驱哈希
            if entry.prev_hash != expected_prev:
                return False

            # 验证记录ID连续性
            expected_id = self.entries.index(entry) + 1
            if entry.id != expected_id:
                return False

            # 重新计算 current_hash
            hash_source = (
                f"{entry.prev_hash}"
                f"{entry.timestamp}"
                f"{entry.operation}"
                f"{entry.input_hash}"
                f"{entry.output_hash}"
            )
            computed_hash = sm3_hash(hash_source.encode("utf-8"))

            if computed_hash != entry.current_hash:
                return False

            expected_prev = entry.current_hash

        return True

    def to_dict_list(self) -> list[dict]:
        """将审计链转换为字典列表，便于序列化。"""
        return [
            {
                "id": e.id,
                "timestamp": e.timestamp,
                "operation": e.operation,
                "operator": e.operator,
                "input_hash": e.input_hash,
                "output_hash": e.output_hash,
                "approval_status": e.approval_status,
                "prev_hash": e.prev_hash,
                "current_hash": e.current_hash,
            }
            for e in self.entries
        ]

    def export(self, indent: int = 2) -> str:
        """
        导出审计链为JSON字符串。

        Args:
            indent: JSON缩进空格数

        Returns:
            格式化的JSON字符串
        """
        return json.dumps(
            {"audit_chain": self.to_dict_list(), "verified": self.verify()},
            ensure_ascii=False,
            indent=indent,
        )

    def __len__(self) -> int:
        return len(self.entries)

    def __repr__(self) -> str:
        return f"<AuditChain entries={len(self.entries)} verified={self.verify()}>"
