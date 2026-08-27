"""
trace.py - eco Agent CLI 可观测轨迹模式（-v/--verbose）

每轮 Agent 循环显示：
    [轮次 N] 💭 思考摘要 → 🔧 调用工具(关键参数) → 👁 结果摘要 → 继续/结束
三角色协作显示各阶段耗时；工作区检索注入显示命中片段数。

所有轨迹事件同时写入 prompt_engine SM3 审计链（source=trace）。
排版使用 rich（克制的样式），Windows 终端经 _safe 降级处理。
"""
from __future__ import annotations

import sys
import time

_IS_WINDOWS = sys.platform.startswith("win")

# Windows 旧终端（GBK cmd）无法输出 emoji 时降级为 ASCII 标记
_FALLBACK = {"💭": "[think]", "🔧": "[tool]", "👁": "[view]",
             "✅": "[done]", "⏭": "[next]"}


def _safe(text: str) -> str:
    if _IS_WINDOWS:
        try:
            text.encode(sys.stdout.encoding or "utf-8")
            return text
        except (UnicodeEncodeError, AttributeError):
            for k, v in _FALLBACK.items():
                text = text.replace(k, v)
            return "".join(c for c in text if ord(c) < 65536)
    return text


def _truncate(text: str, limit: int = 80) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


class Tracer:
    """CLI 轨迹采集与展示。enabled=False 时零开销（事件全部丢弃）。"""

    def __init__(self, enabled: bool = False, audit: bool = True,
                 console=None, think_len: int = 120, result_len: int = 100):
        self.enabled = enabled
        self.think_len = think_len
        self.result_len = result_len
        self._audit_enabled = audit
        self._audit_chain = None
        if console is not None:
            self._console = console
        else:
            try:
                from rich.console import Console
                self._console = Console()
            except ImportError:
                self._console = None
        self.events: list[dict] = []  # 测试/审计用

    # ── 输出 ─────────────────────────────────────────────
    def _emit(self, text: str, style: str = ""):
        if not self.enabled:
            return
        text = _safe(text)
        if self._console is not None:
            self._console.print(text, style=style or None, markup=False)
        else:
            print(text)

    def _audit(self, content: str, phase: str = ""):
        entry = {"ts": time.time(), "phase": phase, "content": content}
        self.events.append(entry)
        if not self._audit_enabled:
            return
        try:
            if self._audit_chain is None:
                from agent_core.prompt_engine import get_prompt_engine
                self._audit_chain = get_prompt_engine().audit
            self._audit_chain.append(source="trace", content=content[:500],
                                     phase=phase, accepted=True)
        except Exception:  # 审计失败不影响主流程
            pass

    # ── Agent 循环事件 ───────────────────────────────────
    def round_start(self, n: int):
        self._emit(f"\n[轮次 {n}]", style="bold #5ae0a0")
        self._audit(f"[轮次 {n}] 开始", phase="round")

    def thought(self, text: str):
        if text:
            t = _truncate(text, self.think_len)
            self._emit(f"  💭 思考: {t}", style="#8a8a8a")
            self._audit(f"💭 思考: {t}", phase="thought")

    def tool_call(self, name: str, args: dict):
        kv = "; ".join(f"{k}={_truncate(v, 30)}" for k, v in list(args.items())[:4])
        self._emit(f"  🔧 调用工具: {name}({kv})", style="#e0b25a")
        self._audit(f"🔧 调用工具: {name}({kv})", phase="tool_call")

    def tool_result(self, name: str, result: str, elapsed: float = 0.0):
        t = _truncate(result, self.result_len)
        tail = f" ({elapsed:.1f}s)" if elapsed else ""
        self._emit(f"  👁 结果: {t}{tail}", style="#6a9ac0")
        self._audit(f"👁 结果[{name}]: {t}", phase="tool_result")

    def finish(self, reason: str = "结束"):
        self._emit(f"  ✅ {reason}", style="#5ae0a0")
        self._audit(f"✅ {reason}", phase="finish")

    # ── 三角色协作事件 ───────────────────────────────────
    def swarm_stage(self, stage: str, detail: str = "", elapsed: float = 0.0):
        tail = f" ({elapsed:.1f}s)" if elapsed else ""
        line = f"[swarm] {stage}" + (f" — {_truncate(detail, 100)}" if detail else "") + tail
        self._emit(line, style="#c08ae0")
        self._audit(line, phase="swarm")

    # ── 系统提示词事件（SOUL 接线可见性）─────────────────
    def system_prompt(self, text: str, soul_loaded: bool = True):
        src = "SOUL" if soul_loaded else "硬编码回退"
        t = _truncate(text.replace("\n", " ⏎ "), 240)
        self._emit(f"  🧬 系统提示词[{src}]: {t}", style="#8a6ac0")
        self._audit(f"🧬 系统提示词[{src}]: {t}", phase="system_prompt")

    # ── 工作区检索注入事件 ───────────────────────────────
    def retrieval(self, hits: int, channel: str = ""):
        if hits > 0:
            line = f"[workspace] 检索注入: 命中 {hits} 个历史片段（{channel or 'bm25'} 检索）"
        else:
            line = "[workspace] 检索注入: 未命中，回退摘要快照"
        self._emit(line, style="#2a8a6a")
        self._audit(line, phase="retrieval")


# ── 全局开关（REPL /verbose 切换用）─────────────────────
_default_tracer = Tracer(enabled=False)


def get_tracer() -> Tracer:
    return _default_tracer


def set_verbose(flag: bool) -> bool:
    _default_tracer.enabled = bool(flag)
    return _default_tracer.enabled
