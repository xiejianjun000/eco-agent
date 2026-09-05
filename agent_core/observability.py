#!/usr/bin/env python3
"""observability.py — 结构化 span 树追踪（llm_call → tool_call 嵌套）

每次 chat 会话生成一棵 span 树：
  session（根）
    └─ llm_call（每轮 LLM 调用：model/tokens/finish_reason/耗时）
         └─ tool_call（该轮触发的工具调用：name/args/result/耗时）

落盘：~/.eco/traces/<session_id>.json（JSON，含扁平 spans 列表，parent_id 关联）。
展示：eco trace --tree <session> 树形渲染；--otel 导出 OTLP JSON（trace v1 资源模型，
无需真实 collector，导出文件即可，可直接喂给 Jaeger/Tempo 的 OTLP ingest）。
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("eco.observability")


def _eco_home() -> Path:
    """ECO_DIR 环境变量优先（沙箱/home 只读时可重定向），默认 ~/.eco。"""
    env = os.environ.get("ECO_DIR", "").strip()
    return Path(env).expanduser() if env else Path.home() / ".eco"


TRACES_DIR = _eco_home() / "traces"


def _default_traces_dir() -> Path:
    """落盘目录：运行时动态读 ECO_DIR，未设置时回退 TRACES_DIR（兼容测试注入）。"""
    env = os.environ.get("ECO_DIR", "").strip()
    return Path(env).expanduser() / "traces" if env else TRACES_DIR


DEFAULT_OTLP_ENDPOINT = "http://localhost:4318"


def trace_id_for_session(session_id: str) -> str:
    """session_id → 确定性 OTLP traceId（32 位十六进制，uuid5 派生）。

    与 decisions.jsonl 的留痕共享同一 id，实现 trace ↔ decision 互查。"""
    return uuid.uuid5(uuid.NAMESPACE_URL, f"eco:{session_id}").hex


# ── 当前活跃 SpanTree 注册（供 decisions 留痕关联 trace_id） ──
_CURRENT_TREE: SpanTree | None = None


def set_current_tree(tree: SpanTree | None) -> None:
    global _CURRENT_TREE
    _CURRENT_TREE = tree


def current_tree() -> SpanTree | None:
    return _CURRENT_TREE


def current_trace_id() -> str:
    """当前活跃会话的 OTLP trace_id；无活跃会话返回空串。"""
    t = _CURRENT_TREE
    return t.trace_id if t is not None else ""


class SpanTree:
    """一次会话的 span 树。线程内顺序执行（chat 主循环），用栈维护嵌套。"""

    def __init__(self, session_id: str = "", meta: dict | None = None):
        self.session_id = session_id or f"{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"
        self.meta = dict(meta or {})
        self.spans: list[dict] = []
        self._stack: list[str] = []
        # 注册为当前活跃树，供 decisions.jsonl 留痕关联 trace_id
        set_current_tree(self)

    @property
    def trace_id(self) -> str:
        """本次会话的 OTLP traceId（确定性派生，可复算）"""
        return trace_id_for_session(self.session_id)

    # ── 记录 ────────────────────────────────────────────
    def start(self, name: str, kind: str, **attrs) -> str:
        """开启一个 span，嵌套到当前栈顶 span 之下，返回 span_id"""
        sid = uuid.uuid4().hex[:16]
        self.spans.append(
            {
                "span_id": sid,
                "parent_id": self._stack[-1] if self._stack else None,
                "name": name,
                "kind": kind,  # session | llm_call | tool_call | dag_step ...
                "start": time.time(),
                "start_iso": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                "end": None,
                "duration_ms": None,
                "attrs": dict(attrs),
            }
        )
        self._stack.append(sid)
        return sid

    def end(self, span_id: str | None = None, **attrs) -> dict | None:
        """结束 span（默认结束栈顶）。attrs 补充到 span.attrs（如 tokens/finish_reason）"""
        if span_id is None:
            if not self._stack:
                return None
            span_id = self._stack[-1]
        span = next((s for s in self.spans if s["span_id"] == span_id), None)
        if span is None or span["end"] is not None:
            return span
        span["end"] = time.time()
        span["duration_ms"] = round((span["end"] - span["start"]) * 1000, 1)
        if attrs:
            span["attrs"].update(attrs)
        # 弹出到该 span（容错：乱序 end 时保持栈一致）
        while self._stack and self._stack[-1] != span_id:
            self._stack.pop()
        if self._stack:
            self._stack.pop()
        return span

    def close_all(self):
        while self._stack:
            self.end()

    # ── 持久化 ──────────────────────────────────────────
    def to_dict(self) -> dict:
        return {"session_id": self.session_id, "meta": self.meta, "spans": self.spans}

    def save(self, directory: Path | None = None) -> Path | None:
        d = Path(directory) if directory else _default_traces_dir()
        try:
            d.mkdir(parents=True, exist_ok=True)
            path = d / f"{self.session_id}.json"
            path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8")
            return path
        except Exception as e:  # noqa: BLE001 — 落盘失败绝不抛错，仅降级告警
            logger.warning("span tree 落盘失败（%s）: %s", d, e)
            return None

    @staticmethod
    def load(session: str, directory: Path | None = None) -> SpanTree:
        """按 session_id 或文件名加载（支持不带 .json 后缀）"""
        d = Path(directory) if directory else _default_traces_dir()
        path = Path(session)
        if not path.exists():
            path = d / (session if session.endswith(".json") else f"{session}.json")
        data = json.loads(path.read_text(encoding="utf-8"))
        tree = SpanTree(session_id=data.get("session_id", path.stem), meta=data.get("meta"))
        tree.spans = list(data.get("spans", []))
        return tree

    @staticmethod
    def list_sessions(directory: Path | None = None) -> list[str]:
        d = Path(directory) if directory else _default_traces_dir()
        if not d.is_dir():
            return []
        return sorted(p.stem for p in d.glob("*.json"))

    # ── 树形渲染 ────────────────────────────────────────
    def render_tree(self) -> str:
        children: dict[str | None, list[dict]] = {}
        for s in self.spans:
            children.setdefault(s.get("parent_id"), []).append(s)
        lines = [f"session {self.session_id}"]

        def _fmt(s: dict) -> str:
            dur = f"{s['duration_ms']:.0f}ms" if s.get("duration_ms") is not None else "…"
            a = s.get("attrs") or {}
            extra = ""
            if s["kind"] == "llm_call":
                toks = []
                if a.get("prompt_tokens") is not None:
                    toks.append(f"in={a['prompt_tokens']}")
                if a.get("completion_tokens") is not None:
                    toks.append(f"out={a['completion_tokens']}")
                extra = f" model={a.get('model', '?')} finish={a.get('finish_reason', '?')}"
                if toks:
                    extra += " tokens(" + ",".join(toks) + ")"
            elif s["kind"] == "tool_call":
                extra = f" args={json.dumps(a.get('args', {}), ensure_ascii=False)[:60]}"
            return f"{s['kind']}:{s['name']} [{dur}]{extra}"

        def _walk(pid, prefix):
            kids = children.get(pid, [])
            for i, s in enumerate(kids):
                last = i == len(kids) - 1
                lines.append(prefix + ("└─ " if last else "├─ ") + _fmt(s))
                _walk(s["span_id"], prefix + ("   " if last else "│  "))

        _walk(None, "")
        return "\n".join(lines)

    # ── OTLP 导出 ───────────────────────────────────────
    def to_otlp(self) -> dict:
        """导出 OTLP trace v1 JSON（resourceSpans 结构，十六进制 trace/span id）"""
        trace_id = self.trace_id

        def _attr(k: str, v) -> dict:
            if isinstance(v, bool):
                val = {"boolValue": v}
            elif isinstance(v, int):
                val = {"intValue": str(v)}
            elif isinstance(v, float):
                val = {"doubleValue": v}
            else:
                val = {"stringValue": json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v)}
            return {"key": k, "value": val}

        otlp_spans = []
        for s in self.spans:
            start_ns = int((s.get("start") or 0) * 1e9)
            end_ns = int((s.get("end") or s.get("start") or 0) * 1e9)
            sp = {
                "traceId": trace_id,
                "spanId": f"{int(s['span_id'], 16):016x}",
                "name": f"{s['kind']}:{s['name']}",
                "kind": 1,  # SPAN_KIND_INTERNAL
                "startTimeUnixNano": str(start_ns),
                "endTimeUnixNano": str(end_ns),
                "attributes": [_attr(k, v) for k, v in (s.get("attrs") or {}).items()] + [_attr("eco.span.kind", s["kind"])],
                "status": {"code": 1},
            }
            if s.get("parent_id"):
                sp["parentSpanId"] = f"{int(s['parent_id'], 16):016x}"
            otlp_spans.append(sp)
        return {
            "resourceSpans": [
                {
                    "resource": {
                        "attributes": [
                            _attr("service.name", "eco-agent"),
                            _attr("eco.session_id", self.session_id),
                        ]
                    },
                    "scopeSpans": [
                        {
                            "scope": {"name": "eco.observability", "version": "1.0"},
                            "spans": otlp_spans,
                        }
                    ],
                }
            ],
        }

    def export_otlp(self, path: Path | str) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_otlp(), ensure_ascii=False, indent=1), encoding="utf-8")
        return p


class OTLPExporter:
    """真实 OTLP/HTTP 导出器（urllib，零新增依赖）。

    POST {endpoint}/v1/traces（OTLP trace v1 JSON）。endpoint 可注入，
    默认读取环境变量 ECO_OTLP_ENDPOINT，缺省 http://localhost:4318。
    任何失败（连接拒绝/超时/非 2xx）降级写本地 span 文件并 warning，
    绝不抛出、不阻塞主流程。
    """

    def __init__(self, endpoint: str | None = None, timeout: float = 5.0, fallback_dir: Path | str | None = None):
        ep = endpoint or os.environ.get("ECO_OTLP_ENDPOINT") or DEFAULT_OTLP_ENDPOINT
        self.endpoint = ep.rstrip("/")
        self.timeout = timeout
        self.fallback_dir = Path(fallback_dir) if fallback_dir else _default_traces_dir()

    @property
    def traces_url(self) -> str:
        return f"{self.endpoint}/v1/traces"

    def export(self, tree: SpanTree) -> bool:
        """导出 span 树到 collector。成功返回 True；失败降级落盘返回 False。"""
        payload = json.dumps(tree.to_otlp(), ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(self.traces_url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        # 内网部署默认不走 http_proxy/https_proxy：collector 多为内网直连
        # （如 http://127.0.0.1:4318），走全局代理反而会连接失败被降级。
        # 显式设 ECO_OTLP_PROXY=1 时才遵循 *_proxy 环境变量经代理导出。
        if os.environ.get("ECO_OTLP_PROXY") == "1":
            opener = urllib.request.build_opener()  # 默认含 ProxyHandler(getproxies())
        else:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(req, timeout=self.timeout) as resp:
                status = getattr(resp, "status", 200)
                if 200 <= status < 300:
                    return True
                raise RuntimeError(f"collector 返回 HTTP {status}")
        except Exception as e:
            logging.warning("[otel] 导出 collector 失败（%s），降级写本地 span 文件", e)
            self._write_fallback(tree)
            return False

    def _write_fallback(self, tree: SpanTree) -> Path:
        path = self.fallback_dir / f"{tree.session_id}.otlp.json"
        return tree.export_otlp(path)
