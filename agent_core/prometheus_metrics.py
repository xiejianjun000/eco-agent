#!/usr/bin/env python3
"""
prometheus_metrics.py — Prometheus 指标导出（对标 SaaS 可观测性要求）

设计：
  - HTTP 指标：进程内 Counter/Histogram，由 server/app.py 的中间件在请求生命周期内采集。
  - LLM/业务指标：从 ~/.eco/stats.jsonl 与运行态汇总为 Gauge（stats.jsonl 是持久化累计记录，
    重启后仍能还原历史累计值，比纯进程内 Counter 更贴合「累计」语义）。
  - 全部指标经 render_metrics() 输出 Prometheus 文本格式（# HELP / # TYPE / name{labels} value）。

依赖：prometheus-client（未安装时优雅降级：render_metrics 返回 503 提示）。
"""
from __future__ import annotations

import logging

logger = logging.getLogger("prometheus_metrics")

try:
    from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

    PROM_AVAILABLE = True
except Exception:  # noqa: BLE001 — 依赖缺失时降级，不阻断 server
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"
    PROM_AVAILABLE = False

    class _Noop:  # 占位：未安装 prometheus-client 时不报错
        def labels(self, *a, **k):  # noqa: ANN001, ANN002, ANN003
            return self

        def inc(self, *a, **k):  # noqa: ANN001, ANN002, ANN003
            pass

        def observe(self, *a, **k):  # noqa: ANN001, ANN002, ANN003
            pass

        def set(self, *a, **k):  # noqa: ANN001, ANN002, ANN003
            pass

    Counter = Gauge = Histogram = _Noop  # type: ignore[misc,assignment]


# ── HTTP 指标（进程内）──
_HTTP_REQUESTS = Counter(
    "eco_http_requests_total",
    "HTTP 请求总数（按方法/路径/状态码）",
    ["method", "path", "status"],
)
_HTTP_DURATION = Histogram(
    "eco_http_request_duration_seconds",
    "HTTP 请求延迟（秒）",
    ["method", "path"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

# ── LLM 指标（从 stats.jsonl 汇总，Gauge 累计）──
_LLM_CALLS = Gauge(
    "eco_llm_calls_total",
    "LLM 调用总数（按 provider/model）",
    ["provider", "model"],
)
_LLM_ERRORS = Gauge(
    "eco_llm_errors_total",
    "LLM 调用错误数（按 provider/model）",
    ["provider", "model"],
)
_LLM_PROMPT_TOKENS = Gauge(
    "eco_llm_prompt_tokens_total",
    "LLM prompt token 累计（按 provider/model）",
    ["provider", "model"],
)
_LLM_COMPLETION_TOKENS = Gauge(
    "eco_llm_completion_tokens_total",
    "LLM completion token 累计（按 provider/model）",
    ["provider", "model"],
)
_LLM_LATENCY_MS_SUM = Gauge(
    "eco_llm_latency_ms_sum",
    "LLM 延迟累计毫秒（按 provider，配合 calls_total 可算均值）",
    ["provider"],
)

# ── 业务指标 ──
_SCHEDULER_JOBS = Gauge("eco_scheduler_jobs", "定时任务数")
_MEMORY_NODES = Gauge("eco_memory_nodes", "记忆树节点数", ["type"])
_APP_INFO = Gauge("eco_app_info", "应用信息（version）", ["version"])


def record_http(method: str, path: str, status: int, duration_s: float) -> None:
    """HTTP 中间件调用：记录一次请求（计数 + 延迟）。"""
    if not PROM_AVAILABLE:
        return
    _HTTP_REQUESTS.labels(method=method, path=path, status=str(status)).inc()
    _HTTP_DURATION.labels(method=method, path=path).observe(duration_s)


def refresh_llm_metrics(stats_file=None) -> None:
    """从 stats.jsonl 汇总 LLM 指标写入 Gauge（幂等，可反复调用）。"""
    if not PROM_AVAILABLE:
        return
    import json as _json
    from pathlib import Path

    path = Path(stats_file) if stats_file else Path.home() / ".eco" / "stats.jsonl"
    recs: list[dict] = []
    if path.exists():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line:
                try:
                    recs.append(_json.loads(line))
                except _json.JSONDecodeError:
                    pass

    agg: dict[tuple[str, str], dict] = {}
    prov: dict[str, int] = {}
    for r in recs:
        provider = r.get("provider", "?")
        model = r.get("model", "?")
        key = (provider, model)
        a = agg.setdefault(key, {"calls": 0, "errors": 0, "pt": 0, "ct": 0})
        a["calls"] += 1
        if not r.get("ok", True):
            a["errors"] += 1
        a["pt"] += r.get("prompt_tokens") or 0
        a["ct"] += r.get("completion_tokens") or 0
        prov[provider] = prov.get(provider, 0) + (r.get("latency_ms") or 0)

    for (provider, model), a in agg.items():
        _LLM_CALLS.labels(provider=provider, model=model).set(a["calls"])
        _LLM_ERRORS.labels(provider=provider, model=model).set(a["errors"])
        _LLM_PROMPT_TOKENS.labels(provider=provider, model=model).set(a["pt"])
        _LLM_COMPLETION_TOKENS.labels(provider=provider, model=model).set(a["ct"])
    for provider, ms in prov.items():
        _LLM_LATENCY_MS_SUM.labels(provider=provider).set(ms)


def refresh_business_metrics(scheduler_jobs: int = 0, memory_nodes: dict | None = None) -> None:
    """写入调度/记忆等业务 Gauge。"""
    if not PROM_AVAILABLE:
        return
    _SCHEDULER_JOBS.set(scheduler_jobs)
    for typ, n in (memory_nodes or {}).items():
        _MEMORY_NODES.labels(type=typ).set(n)


def set_app_info(version: str) -> None:
    """应用版本信息（Gauge 恒定 1，label 携带版本）。"""
    if not PROM_AVAILABLE:
        return
    _APP_INFO.labels(version=version).set(1)


def render_metrics() -> tuple[str, str]:
    """生成 Prometheus 文本；未安装依赖时返回 503 提示。"""
    if not PROM_AVAILABLE:
        return "text/plain; charset=utf-8", (
            "# prometheus-client not installed\n"
            "# install: pip install prometheus-client\n"
        )
    return CONTENT_TYPE_LATEST, generate_latest().decode("utf-8")
