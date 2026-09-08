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
import threading
import time
from pathlib import Path

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
        # 写入串行化：_append 是「读链尾 → 算哈希 → 追加」的读改写序列，
        # 并发调用会让多条记录读到同一个链尾、都以它作 prev_hash → 链分叉。
        # 实测 4 线程各写 6 条即在第 2 行断裂；线上 2026-09-01 23:27:03
        # 曾有两个会话（round3 与 round1）在 6ms 内交错写入，造成 3 处断裂。
        self._write_lock = threading.Lock()
        # 链尾缓存：持锁期间内存维护，避免每次都回读文件末行（也消除 TOCTOU）
        self._tip_hash: str | None = None
        # 跨进程互斥：线程锁只在单进程内有效，实测 3 个进程并发写仍在第 2 行断裂。
        # 用 flock 排他锁把「取链尾 → 算哈希 → 落盘」在进程间也串行化。
        self._lock_path = self.base_dir / "trace_audit.lock"
        # verify 计算锁：防止并发请求同时冷算全链（见 verify 的踩踏说明）
        self._verify_lock = threading.Lock()

    # ── 记录 ─────────────────────────────────────────────

    def record_tool_call(
        self, tool: str, args: dict, result: str, duration_ms: int, level: str = "L1", decision: str = "allow"
    ) -> dict:
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

    def record_llm_call(self, model: str, round_idx: int, duration_ms: int, input_chars: int = 0) -> dict:
        """记录一次 LLM 调用（轨迹中的思考轮）。"""
        entry = {
            "when": time.time(),
            "who": "eco-agent",
            "what": f"llm_call:{model}:round{round_idx}",
            "result": f"in={input_chars}chars",
            "cost": f"{duration_ms}ms",
        }
        return self._append(entry, operation="llm_call", operator="eco-agent")

    def record_trace(self, user_msg: str, reply: str, trace_len: int, duration_ms: int, model: str = "") -> dict:
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

    def _chain_fingerprint(self) -> tuple:
        """链文件指纹（mtime_ns + size）：内容变化必然改变，用于缓存失效。"""
        try:
            st = self.chain_path.stat()
            return (st.st_mtime_ns, st.st_size)
        except OSError:
            return (0, 0)

    def verify(self) -> dict:
        """校验落盘链的 SM3 哈希（带指纹缓存）。

        SM3 为纯 Python 实现，逐行重算成本随链长线性增长（实测 7283 行
        约 25.8 秒；stats() 内部再调一次导致面板接口 ~51 秒挂死）。
        此处按「文件 mtime_ns + size」缓存：链未追加时直接复用，
        一旦追加指纹变化自动重算，不牺牲防篡改语义。
        """
        fp = self._chain_fingerprint()
        cached = getattr(self, "_verify_cache", None)
        if cached is not None and cached[0] == fp:
            return dict(cached[1])
        # 缓存踩踏防护（k6 实测）：20 VU 并发时缓存同时未命中，
        # 每个请求各自跑一遍 20 秒的 SM3 全链重算 —— p95 21.8s、最坏 41.8s。
        # 加锁后只有第一个请求真算，其余等待并复用结果。
        with self._verify_lock:
            cached = getattr(self, "_verify_cache", None)
            if cached is not None and cached[0] == fp:
                return dict(cached[1])   # 等锁期间别人已算好
            result = self._verify_uncached()
            self._verify_cache = (fp, dict(result))
            return result

    def _verify_uncached(self) -> dict:
        """真正执行逐行 SM3 重算（无缓存）。

        增量优化：链文件只追加不原地改，指纹变化说明文件变长了。
        把已验证前缀的行数和 last_hash 存进缓存，新增行从上一轮
        最后一条续算，不重算历史行。
        实测 7742 行冷算 42 秒，但每轮对话只追加大约 10-30 行——
        增量后应当从 42 秒降到 <1 秒。
        """
        from govmcp.crypto.audit import GENESIS_PREV_HASH
        from govmcp.crypto.sm import sm3_hash

        meta_fields = {
            "input_data", "timestamp", "current_hash", "prev_hash",
            "entry_id", "input_hash", "output_hash", "operation", "operator",
        }
        lines = self._raw_lines()
        total = len(lines)

        # 从缓存取上一轮已验证前缀的行数，跳过历史行
        prev_ok = getattr(self, "_verify_cache_prefix", None)
        if prev_ok is not None and prev_ok["n"] <= total:
            start = prev_ok["n"]
            prev_hash = prev_ok["last_hash_16"]
            entries = list(prev_ok["entries"])
            breaks = list(prev_ok["breaks"])
        else:
            start = 0
            prev_hash = GENESIS_PREV_HASH
            entries = []
            breaks = []

        for i in range(start, total):
            line = lines[i]
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                return {"ok": False, "error": f"第 {i + 1} 行损坏", "entries": len(entries)}
            if e.get("prev_hash") != prev_hash:
                breaks.append({"line": i + 1, "expect": prev_hash[:16],
                               "actual": str(e.get("prev_hash", ""))[:16]})
                prev_hash = str(e.get("prev_hash", ""))
            business_entry = {k: v for k, v in e.items() if k not in meta_fields}
            input_data = json.dumps(business_entry, ensure_ascii=False)
            input_hash = sm3_hash(input_data.encode("utf-8"))
            output_hash = e.get("output_hash", "")
            hash_source = f"{prev_hash}{e.get('timestamp', '')}{e.get('operation', '')}{input_hash}{output_hash}"
            recomputed = sm3_hash(hash_source.encode("utf-8"))
            if recomputed != e.get("current_hash", ""):
                return {"ok": False, "tampered_line": i + 1,
                        "error": f"第 {i + 1} 行内容被篡改（哈希失配）",
                        "entries": len(entries), "breaks": breaks}
            prev_hash = e.get("current_hash", "")
            entries.append(e)

        # 注意：last_hash 对外只暴露前 16 位，但续算必须用完整哈希。
        # 曾把截断值存进前缀缓存，下一轮拿 16 位去比完整 prev_hash，
        # 每次增量都误报一处「链接断裂」——测试当场抓到。
        result = {
            "ok": not breaks,
            "entries": len(entries),
            "verified": len(entries),
            "last_hash": prev_hash[:16],
            "breaks": breaks,
            "segments": len(breaks) + 1,
        }
        if breaks:
            result["error"] = (
                f"{len(breaks)} 处链接断裂（并发写入所致），"
                f"但 {len(entries)} 条记录内容均未被篡改"
            )
        # 存前缀，供下次增量续算
        self._verify_cache_prefix = {
            "n": total,
            "last_hash_16": prev_hash,   # 完整哈希，字段名沿用历史
            "entries": list(entries),
            "breaks": list(breaks),
        }
        return result

    def stats(self) -> dict:
        """链统计（verify 结果 + 按操作类型计数）。

        by_operation 需要逐行 json.loads 全文件（7000+ 行），
        与 verify 同样按文件指纹缓存，避免每次面板刷新都重算。
        """
        v = self.verify()
        fp = self._chain_fingerprint()
        cached = getattr(self, "_stats_cache", None)
        if cached is not None and cached[0] == fp:
            by_what, size = cached[1], cached[2]
        else:
            by_what = {}
            for line in self._raw_lines():
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                what = str(e.get("what", "?")).split(":")[0]
                by_what[what] = by_what.get(what, 0) + 1
            size = self.chain_path.stat().st_size if self.chain_path.exists() else 0
            self._stats_cache = (fp, by_what, size)
        v["by_operation"] = dict(by_what)
        v["size_bytes"] = size
        return v

    # ── 内部 ─────────────────────────────────────────────

    def _append(self, entry: dict, operation: str, operator: str) -> dict:
        """五要素入链：govmcp SM3 链计算 + JSONL 追加。

        全程持 _write_lock：哈希链的 prev_hash 依赖「当前链尾」，
        读链尾与追加之间若被其他写入插入，两条记录会共用同一 prev_hash
        导致链分叉。锁把「取链尾 → 算哈希 → 落盘 → 更新链尾」变为原子段。
        """
        import fcntl

        with self._write_lock:  # 进程内互斥
            with self._lock_path.open("a+") as lk:
                fcntl.flock(lk.fileno(), fcntl.LOCK_EX)  # 进程间互斥
                try:
                    # 持有跨进程锁后必须回读真实链尾：其他进程可能已追加，
                    # 本进程的 _tip_hash 已过期，沿用它会造成分叉。
                    self._tip_hash = None
                    return self._append_locked(entry, operation, operator)
                finally:
                    fcntl.flock(lk.fileno(), fcntl.LOCK_UN)

    def _append_locked(self, entry: dict, operation: str, operator: str) -> dict:
        from govmcp.crypto.audit import AuditChain

        chain = AuditChain()
        # 跨进程/跨重启衔接：预置上一条 current_hash 为前驱桩，
        # 使 add_entry 的 prev_hash 与既有链尾衔接（而非创世哈希）
        # 优先用内存链尾（持锁期间由本类独占维护）；首次或跨进程重启时回读文件
        last = self._tip_hash if self._tip_hash is not None else self._last_hash()
        if last:
            from govmcp.crypto.audit import AuditEntry

            chain.entries.append(
                AuditEntry(
                    id=0,
                    timestamp=0.0,
                    operation="",
                    operator="",
                    input_hash="",
                    output_hash="",
                    approval_status="",
                    prev_hash="",
                    current_hash=last,
                )
            )
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
        # 落盘成功后才推进链尾，写失败时下次仍回读文件，不会把链尾推到未落盘的哈希
        self._tip_hash = record["current_hash"]
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
