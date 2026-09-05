#!/usr/bin/env python3
"""
cost_ledger.py — per-delegation 成本账本（P0-4 Steering 深化）

对标 Hermes Live Steering / cost capture：
- 每次 delegation（子任务执行）记录一条 ledger entry：
  task_id / agent_id / role / 起止时间 / 耗时 / LLM 调用数 / tokens / 估算成本(USD)
- mission 结束输出可审计汇总：总 delegation、总耗时、总成本、成本 Top-N
- 不依赖第三方库；LLM usage 由 llm_client 侧统计，此处仅做记账与汇总。
"""

import threading
import time
from datetime import datetime

# 估算单价：prompt / completion per 1K tokens（USD），兜底常量
DEFAULT_PRICES = {"prompt": 0.00015, "completion": 0.00060}
TOKEN_FALLBACK_PER_CALL = 800  # 无 token 明细时的单次 LLM 调用粗估 tokens


class CostLedger:
    """线程安全的 delegation 成本账本。"""

    def __init__(self, prices: dict | None = None):
        self._prices = dict(DEFAULT_PRICES if prices is None else prices)
        self._entries: list[dict] = []
        self._lock = threading.Lock()

    def open(self, task_id: str, agent_id: str, role: str = "") -> str:
        """打开一次 delegation 记账，返回 entry_id（异常安全：无真实副作用）。"""
        eid = f"dlg_{int(time.time() * 1000)}_{len(self._entries)}"
        with self._lock:
            self._entries.append(
                {
                    "entry_id": eid,
                    "task_id": task_id,
                    "agent_id": agent_id,
                    "role": role,
                    "started_at": datetime.now().isoformat(timespec="seconds"),
                    "ended_at": "",
                    "duration_ms": 0.0,
                    "llm_calls": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "est_cost_usd": 0.0,
                    "status": "running",
                }
            )
        return eid

    def close(
        self,
        entry_id: str,
        *,
        llm_calls: int = 0,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        status: str = "completed",
    ) -> None:
        """关闭一次 delegation 记账：写耗时、token 用量与估算成本。"""
        with self._lock:
            for e in self._entries:
                if e["entry_id"] == entry_id:
                    e["ended_at"] = datetime.now().isoformat(timespec="seconds")
                    try:
                        start = datetime.fromisoformat(e["started_at"])
                        end = datetime.fromisoformat(e["ended_at"])
                        e["duration_ms"] = round((end - start).total_seconds() * 1000, 1)
                    except ValueError:
                        e["duration_ms"] = 0.0
                    e["llm_calls"] = llm_calls
                    e["prompt_tokens"] = prompt_tokens
                    e["completion_tokens"] = completion_tokens
                    e["est_cost_usd"] = self._estimate(prompt_tokens, completion_tokens, llm_calls)
                    e["status"] = status
                    return

    @staticmethod
    def _estimate(prompt_tokens: int, completion_tokens: int, llm_calls: int) -> float:
        pt = prompt_tokens or (llm_calls * TOKEN_FALLBACK_PER_CALL // 2)
        ct = completion_tokens or (llm_calls * TOKEN_FALLBACK_PER_CALL // 2)
        usd = pt / 1000 * DEFAULT_PRICES["prompt"] + ct / 1000 * DEFAULT_PRICES["completion"]
        return round(usd, 6)

    def snapshot(self) -> list[dict]:
        with self._lock:
            return list(self._entries)

    def summary(self) -> dict:
        entries = self.snapshot()
        if not entries:
            return {
                "delegations": 0,
                "total_duration_ms": 0.0,
                "total_llm_calls": 0,
                "total_tokens": 0,
                "total_cost_usd": 0.0,
                "top_cost": [],
            }
        total_ms = sum(e["duration_ms"] for e in entries)
        total_llm = sum(e["llm_calls"] for e in entries)
        total_tok = sum(e["prompt_tokens"] + e["completion_tokens"] for e in entries)
        total_usd = round(sum(e["est_cost_usd"] for e in entries), 6)
        top = sorted(entries, key=lambda x: x["est_cost_usd"], reverse=True)[:5]
        return {
            "delegations": len(entries),
            "total_duration_ms": round(total_ms, 1),
            "total_llm_calls": total_llm,
            "total_tokens": total_tok,
            "total_cost_usd": total_usd,
            "top_cost": [
                {
                    "task_id": e["task_id"],
                    "duration_ms": e["duration_ms"],
                    "llm_calls": e["llm_calls"],
                    "est_cost_usd": e["est_cost_usd"],
                }
                for e in top
            ],
        }


class LedgerReporter:
    """把 ledger 渲染成人类可读文本 / JSON（供 CLI / REST 消费）。"""

    @staticmethod
    def render_plain(summ: dict) -> str:
        lines = [
            f"  delegations     : {summ['delegations']}",
            f"  总耗时          : {summ['total_duration_ms']} ms",
            f"  LLM 调用        : {summ['total_llm_calls']}",
            f"  tokens          : {summ['total_tokens']}",
            f"  估算成本        : ${summ['total_cost_usd']}",
        ]
        if summ["top_cost"]:
            lines.append("  成本 Top:")
            for t in summ["top_cost"]:
                lines.append(f"    {t['task_id']}: {t['duration_ms']}ms llm={t['llm_calls']} ${t['est_cost_usd']}")
        return "\n".join(lines)
