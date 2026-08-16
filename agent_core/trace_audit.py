#!/usr/bin/env python3
"""
agent_core/trace_audit.py — 执行轨迹审计（govmcp SM3 审计链 + 五要素台账）

等保三级"完整可审计、不可篡改、可追溯"的落地模块：
  - 每条轨迹事件 = (when, who, what, result, cost) 五要素
  - 事件经 govmcp.crypto.audit.AuditChain（SM3 哈希链）锁定，
    前驱哈希衔接防篡改，链尾哈希可对外出示
  - 落盘 JSONL（~/.eco 或注入目录），verify() 可整体校验
  - 与 session_log（SHA-256 事实流）互补：本模块是"等保审计证据"，
    session_log 是"会话事实重放"

用法:
    audit = TraceAudit()                # 进程级单例（get_trace_audit）
    audit.record_tool_call(tool, args, result, duration_ms, level, decision)
    audit.record_trace(user_msg, reply, trace_summary, duration_ms, model)
    audit.verify()                      # 校验整条链
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("eco.trace_audit")

DATA_DIR = Path(__file__).resolve().parent.parent / "memory-tree" / "data"

# 五要素字段名（等保审计口径）
FIVE_ELEMENTS = ("when", "who", "what", "result", "cost")


class TraceAudit:
    """执行轨迹审计链（govmcp SM3 + JSONL 落盘）。"""

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = Path(base_dir) if base_dir else DATA_DIR / "audit"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.chain_path = self.base_dir / "trace_audit.jsonl"
        self._chain = self._load_chain()

    # ── 记录 ─────────────────────────────────────────────

    def record_tool_call(self, tool: str, args: dict, result: str,
                         duration_ms: int, level: str = "L1",
                         decision: str = "allow") -> dict:
        """记录一次工具调用（五要素 + SM3 入链）。"""
        entry = {
            "when": time.time(),
            "who": "eco-agent",
            "what": f"tool_call:{tool}",
            "result": (str(result)[:500]),
            "cost": f"{duration_ms}ms",
            "level": level,
            "decision": decision,
        }
        return self._append(entry, operation="tool_call", operator="eco-agent")

    def record_llm_call(self, model: str, round_idx: int, duration_ms: int,
                        input_chars: int = 0) -> dict:
        """记录一次 LLM 调用（轨迹中的思考轮）。"""
        entry = {
            "when": time.time(),
            "who": "eco-agent",
            "what": f"llm_call:{model}:round{round_idx}",
            "result": f"in={input_chars}chars",
            "cost": f"{duration_ms}ms",
        }
        return self._append(entry, operation="llm_call", operator="eco-agent")

    def record_trace(self, user_msg: str, reply: str, trace_len: int,
                     duration_ms: int, model: str = "") -> dict:
        """记录整条对话轨迹摘要（含用户输入与最终回答指纹）。"""
        entry = {
            "when": time.time(),
            "who": "eco-agent",
            "what": f"chat_trace:{model}",
            "result": f"trace_steps={trace_len}, reply_chars={len(reply)}",
            "cost": f"{duration_ms}ms",
            "user_hash": _sm3_hex(user_msg.encode("utf-8"))[:16],
            "reply_hash": _sm3_hex(reply.encode("utf-8"))[:16],
        }
        return self._append(entry, operation="chat_trace", operator="eco-agent")

    # ── 校验 ─────────────────────────────────────────────

    def verify(self) -> dict:
        """校验落盘链的 SM3 哈希（重算比对，防篡改检测）。

        每行重算: input_hash' = sm3(input_data)，
        current_hash' = sm3(prev_hash + timestamp + operation + input_hash' + output_hash)，
        与落盘 current_hash 比对；任何内容篡改必然哈希失配。
        """
        from govmcp.crypto.audit import GENESIS_PREV_HASH
        from govmcp.crypto.sm import sm3_hash

        # 审计元字段（重算 input 时排除，其余字段即入链时的业务 entry）
        meta_fields = {"input_data", "timestamp", "current_hash", "prev_hash",
                       "entry_id", "input_hash", "output_hash", "operation", "operator"}
        lines = self._raw_lines()
        prev_hash = GENESIS_PREV_HASH  # 创世前驱与 govmcp AuditChain 一致
        entries = []
        for i, line in enumerate(lines):
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                return {"ok": False, "error": f"第 {i + 1} 行损坏", "entries": len(entries)}
            if e.get("prev_hash") != prev_hash:
                return {"ok": False, "error": f"第 {i + 1} 行哈希链断裂", "entries": len(entries)}
            # 从当前行业务字段重建入链 input（业务字段被篡改必然改变重建结果）
            business_entry = {k: v for k, v in e.items() if k not in meta_fields}
            input_data = json.dumps(business_entry, ensure_ascii=False)
            input_hash = sm3_hash(input_data.encode("utf-8"))
            output_hash = e.get("output_hash", "")
            hash_source = f"{prev_hash}{e.get('timestamp', '')}{e.get('operation', '')}{input_hash}{output_hash}"
            recomputed = sm3_hash(hash_source.encode("utf-8"))
            if recomputed != e.get("current_hash", ""):
                return {"ok": False, "error": f"第 {i + 1} 行内容被篡改（哈希失配）",
                        "entries": len(entries)}
            prev_hash = e.get("current_hash", "")
            entries.append(e)
        return {"ok": True, "entries": len(entries), "last_hash": prev_hash[:16]}

    def stats(self) -> dict:
        v = self.verify()
        by_what: dict[str, int] = {}
        for line in self._raw_lines():
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            what = str(e.get("what", "?")).split(":")[0]
            by_what[what] = by_what.get(what, 0) + 1
        v["by_operation"] = by_what
        v["size_bytes"] = self.chain_path.stat().st_size if self.chain_path.exists() else 0
        return v

    # ── 内部 ─────────────────────────────────────────────

    def _append(self, entry: dict, operation: str, operator: str) -> dict:
        """五要素入链：govmcp SM3 链计算 + JSONL 追加。"""
        from govmcp.crypto.audit import AuditChain

        chain = AuditChain()
        # 跨进程/跨重启衔接：预置上一条 current_hash 为前驱桩，
        # 使 add_entry 的 prev_hash 与既有链尾衔接（而非创世哈希）
        last = self._last_hash()
        if last:
            from govmcp.crypto.audit import AuditEntry

            chain.entries.append(AuditEntry(
                id=0, timestamp=0.0, operation="", operator="",
                input_hash="", output_hash="", approval_status="",
                prev_hash="", current_hash=last))
        audit_entry = chain.add_entry(
            operation=operation,
            operator=operator,
            input_data=json.dumps(entry, ensure_ascii=False).encode("utf-8"),
            output_data=b"",
            approval_status="approved",
        )
        record = {
            **entry,
            "operation": operation,
            "operator": operator,
            # 使用审计条目实际计算时的 prev_hash（创世记录为 GENESIS_PREV_HASH）
            "prev_hash": audit_entry.prev_hash,
            "current_hash": audit_entry.current_hash,
            "entry_id": audit_entry.id,
            # 重算所需（verify 防篡改）：
            "input_data": json.dumps(entry, ensure_ascii=False),
            "timestamp": audit_entry.timestamp,
            "input_hash": audit_entry.input_hash,
            "output_hash": audit_entry.output_hash,
        }
        with self.chain_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            f.flush()
            import os
            os.fsync(f.fileno())
        return record

    def _last_hash(self) -> str:
        lines = self._raw_lines()
        if not lines:
            return ""
        try:
            return json.loads(lines[-1]).get("current_hash", "")
        except json.JSONDecodeError:
            return ""

    def _load_chain(self):
        from govmcp.crypto.audit import AuditChain

        chain = AuditChain()
        return chain

    def _raw_lines(self) -> list[str]:
        if not self.chain_path.exists():
            return []
        return self.chain_path.read_text(encoding="utf-8", errors="replace").splitlines()


def _sm3_hex(data: bytes) -> str:
    from govmcp.crypto.sm import sm3_hash

    return sm3_hash(data)


# 进程级单例
_default_audit: TraceAudit | None = None


def get_trace_audit(base_dir: Path | None = None) -> TraceAudit:
    global _default_audit
    if _default_audit is None:
        _default_audit = TraceAudit(base_dir)
    return _default_audit
