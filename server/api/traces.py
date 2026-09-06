#!/usr/bin/env python3
"""
server/api/traces.py — 观测数据 API（轨迹 / 决策 / 统计 / 检查点）

补齐轨迹数据的 Web 暴露面（此前仅 /chat/stream 的 SSE 实时推进，刷新即丢）：

  GET  /api/v1/traces                        span 树摘要列表（~/.eco/traces/*.json，按时间倒序）
  GET  /api/v1/traces/{session_id}           完整 span 树（attrs 字符串截断 2000 字符，防敏感原文外泄）
  GET  /api/v1/decisions?limit&offset        LLM 决策时间线（decisions.jsonl，SM3 链，倒序分页）
  GET  /api/v1/stats/summary                 LLM 调用聚合（按 provider/model/日期 + 成本估算）
  GET  /api/v1/checkpoints/{session}         会话检查点列表
  POST /api/v1/checkpoints/{session}/rewind  回滚到第 n 个检查点（还原工作区文件 + 截断检查点时间线）

成本估算口径：服务端维护 MODEL_PRICE_PER_M（元/百万 tokens），前端不再硬编码。
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger("eco.server.traces")

router = APIRouter()

# session_id 白名单：防路径穿越（与 server/api/sessions.py 同规则）
_SID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")

# attrs 内字符串截断上限（tool result 等可能含敏感原文）
MAX_ATTR_CHARS = 2000

# 模型计价表（元/百万 tokens：input, output；估算口径，按官方价目表维护）。
# 命中规则：精确匹配 → 最长前缀匹配 → 默认价。
MODEL_PRICE_PER_M: dict[str, tuple[float, float]] = {
    "deepseek-chat": (2.0, 8.0),
    "deepseek-reasoner": (4.0, 16.0),
    "deepseek-v4": (4.0, 16.0),
    "kimi-k2": (4.0, 16.0),
    "moonshot-v1-8k": (12.0, 12.0),
    "moonshot-v1-32k": (24.0, 24.0),
    "moonshot-v1-128k": (60.0, 60.0),
    "qwen-turbo": (2.0, 6.0),
    "qwen-plus": (4.0, 12.0),
    "qwen-max": (40.0, 120.0),
}
DEFAULT_PRICE_PER_M = (4.0, 16.0)


def price_for_model(model: str) -> tuple[tuple[float, float], str]:
    """返回 ((input, output), 命中规则)；查不到走默认价"""
    m = (model or "").strip().lower()
    if m in MODEL_PRICE_PER_M:
        return MODEL_PRICE_PER_M[m], "exact"
    best = ""
    for key in MODEL_PRICE_PER_M:
        if m.startswith(key) and len(key) > len(best):
            best = key
    if best:
        return MODEL_PRICE_PER_M[best], f"prefix:{best}"
    return DEFAULT_PRICE_PER_M, "default"


def _check_sid(session_id: str) -> None:
    if not _SID_RE.match(session_id or ""):
        raise HTTPException(status_code=400, detail="非法 session_id")


def _traces_dir() -> Path:
    from agent_core.observability import _default_traces_dir  # noqa: SLF001

    return _default_traces_dir()


def _truncate_attrs(v, limit: int = MAX_ATTR_CHARS):
    """递归截断 attrs 内超长字符串（result/args 可能含敏感原文）"""
    if isinstance(v, str):
        return v if len(v) <= limit else v[:limit] + f"…[truncated {len(v) - limit} chars]"
    if isinstance(v, dict):
        return {k: _truncate_attrs(x, limit) for k, x in v.items()}
    if isinstance(v, list):
        return [_truncate_attrs(x, limit) for x in v]
    return v


def _trace_summary(path: Path) -> dict | None:
    """单个 trace 文件的摘要；损坏文件跳过（返回 None）"""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("[traces] 跳过损坏 trace %s: %s", path.name, e)
        return None
    spans = data.get("spans") or []
    starts = [s.get("start") for s in spans if isinstance(s.get("start"), (int, float))]
    ends = [s.get("end") for s in spans if isinstance(s.get("end"), (int, float))]
    start = min(starts) if starts else path.stat().st_mtime
    duration_ms = round((max(ends) - start) * 1000, 1) if ends else None
    start_iso = next((s.get("start_iso") for s in spans if s.get("start_iso")), "")
    if not start_iso:
        start_iso = datetime.fromtimestamp(start).astimezone().isoformat(timespec="milliseconds")
    ptoks = ctoks = 0
    llm_calls = tool_calls = 0
    for s in spans:
        a = s.get("attrs") or {}
        if s.get("kind") == "llm_call":
            llm_calls += 1
            ptoks += a.get("prompt_tokens") or 0
            ctoks += a.get("completion_tokens") or 0
        elif s.get("kind") == "tool_call":
            tool_calls += 1
    session_id = data.get("session_id") or path.stem
    from agent_core.observability import trace_id_for_session

    return {
        "session_id": session_id,
        "trace_id": trace_id_for_session(session_id),
        "meta": data.get("meta") or {},
        "span_count": len(spans),
        "llm_calls": llm_calls,
        "tool_calls": tool_calls,
        "start": start,
        "start_iso": start_iso,
        "duration_ms": duration_ms,
        "prompt_tokens": ptoks,
        "completion_tokens": ctoks,
    }


@router.get("/traces")
async def list_traces(limit: int = Query(default=100, ge=1, le=1000)) -> dict:
    """span 树摘要列表（按开始时间倒序）"""
    d = _traces_dir()
    items = []
    if d.is_dir():
        for p in d.glob("*.json"):
            s = _trace_summary(p)
            if s is not None:
                items.append(s)
    items.sort(key=lambda x: x["start"], reverse=True)
    return {"count": len(items), "items": items[:limit]}


@router.get("/traces/{session_id}")
async def get_trace(session_id: str) -> dict:
    """完整 span 树（attrs 字符串截断到 2000 字符）"""
    _check_sid(session_id)
    path = _traces_dir() / f"{session_id}.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="trace not found")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        raise HTTPException(status_code=422, detail="trace 文件损坏") from None
    for s in data.get("spans") or []:
        if isinstance(s.get("attrs"), dict):
            s["attrs"] = _truncate_attrs(s["attrs"])
    from agent_core.observability import trace_id_for_session

    data["trace_id"] = trace_id_for_session(data.get("session_id") or session_id)
    return data


@router.get("/decisions")
async def list_decisions(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    trace_id: str = Query(default="", description="按 trace_id 过滤（关联某次会话的决策）"),
) -> dict:
    """LLM 决策时间线（decisions.jsonl 倒序分页，content 内嵌 JSON 已解析）"""
    from agent_core.decisions import DECISIONS_FILE

    items: list[dict] = []
    if DECISIONS_FILE.exists():
        for line in DECISIONS_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if entry.get("source") != "llm_decision":
                    continue
                payload = json.loads(entry.get("content", "{}"))
                if not isinstance(payload, dict):
                    continue
            except (json.JSONDecodeError, TypeError):
                continue
            items.append({
                "ts": entry.get("ts", ""),
                "hash": entry.get("hash", ""),
                "candidate_tools": payload.get("candidate_tools", 0),
                "selected_tools": payload.get("selected_tools") or [],
                "finish_reason": payload.get("finish_reason", ""),
                "prompt_phase": payload.get("prompt_phase", ""),
                "model": payload.get("model", ""),
                "provider": payload.get("provider", ""),
                "round": payload.get("round", 0),
                "trace_id": payload.get("trace_id", ""),
            })
    items.sort(key=lambda x: x["ts"], reverse=True)
    if trace_id:
        items = [x for x in items if x["trace_id"] == trace_id]
    return {"total": len(items), "offset": offset, "limit": limit,
            "items": items[offset:offset + limit]}


def _new_agg() -> dict:
    return {"calls": 0, "errors": 0, "prompt_tokens": 0, "completion_tokens": 0,
            "latency_ms_sum": 0.0, "cost_yuan": 0.0}


def _fold_agg(agg: dict, rec: dict, price: tuple[float, float]) -> None:
    agg["calls"] += 1
    if not rec.get("ok", True):
        agg["errors"] += 1
    pt = rec.get("prompt_tokens") or 0
    ct = rec.get("completion_tokens") or 0
    agg["prompt_tokens"] += pt
    agg["completion_tokens"] += ct
    agg["latency_ms_sum"] += rec.get("latency_ms") or 0.0
    agg["cost_yuan"] += (pt * price[0] + ct * price[1]) / 1_000_000


def _fin_agg(agg: dict) -> dict:
    calls = agg["calls"]
    return {
        "calls": calls,
        "errors": agg["errors"],
        "prompt_tokens": agg["prompt_tokens"],
        "completion_tokens": agg["completion_tokens"],
        "total_tokens": agg["prompt_tokens"] + agg["completion_tokens"],
        "avg_latency_ms": round(agg["latency_ms_sum"] / max(calls, 1), 1),
        "cost_yuan": round(agg["cost_yuan"], 6),
    }


@router.get("/stats/summary")
async def stats_summary() -> dict:
    """聚合 stats.jsonl：按 provider/model/日期的 calls/errors/tokens/avg_latency/成本。

    成本按 MODEL_PRICE_PER_M（元/百万 tokens）估算，查不到模型走默认价；
    pricing 字段回传计价表供前端复用（替换前端硬编码 PRICE_PER_M）。"""
    from agent_core.llm_client import STATS_FILE

    recs: list[dict] = []
    if STATS_FILE.exists():
        for line in STATS_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(rec, dict):
                recs.append(rec)

    total = _new_agg()
    by_provider: dict[str, dict] = {}
    by_model: dict[str, dict] = {}
    by_date: dict[str, dict] = {}
    model_provider: dict[str, str] = {}
    for r in recs:
        model = r.get("model") or "?"
        provider = r.get("provider") or "?"
        price, _rule = price_for_model(model)
        _fold_agg(total, r, price)
        _fold_agg(by_provider.setdefault(provider, _new_agg()), r, price)
        _fold_agg(by_model.setdefault(model, _new_agg()), r, price)
        model_provider.setdefault(model, provider)
        day = str(r.get("ts") or "")[:10] or "?"
        _fold_agg(by_date.setdefault(day, _new_agg()), r, price)

    return {
        "total": _fin_agg(total),
        "by_provider": {k: _fin_agg(v) for k, v in sorted(by_provider.items())},
        "by_model": [
            {"model": m, "provider": model_provider.get(m, "?"),
             "price_per_m": {"input": price_for_model(m)[0][0], "output": price_for_model(m)[0][1],
                             "rule": price_for_model(m)[1]},
             **_fin_agg(v)}
            for m, v in sorted(by_model.items(), key=lambda kv: -kv[1]["calls"])
        ],
        "by_date": [
            {"date": d, **_fin_agg(v)} for d, v in sorted(by_date.items(), reverse=True)
        ],
        "pricing": {
            "unit": "CNY per 1M tokens",
            "default": {"input": DEFAULT_PRICE_PER_M[0], "output": DEFAULT_PRICE_PER_M[1]},
            "models": {k: {"input": v[0], "output": v[1]} for k, v in MODEL_PRICE_PER_M.items()},
        },
        "stats_file": str(STATS_FILE),
    }


class RewindBody(BaseModel):
    n: int = Field(..., ge=1, description="回滚到第 n 个检查点")


def _checkpoint_store(session: str):
    from agent_core.checkpoint import CheckpointStore

    return CheckpointStore(session=session)


def _cp_summary(cp: dict) -> dict:
    """检查点摘要（不回传完整 history/文件内容，避免响应过大）"""
    ws = cp.get("workspace") or {}
    return {
        "id": cp.get("id"),
        "session": cp.get("session", ""),
        "ts": cp.get("ts", ""),
        "history_len": len(cp.get("history") or []),
        "decisions_count": cp.get("decisions_count", 0),
        "workspace_slug": ws.get("slug", ""),
        "workspace_files": sorted((ws.get("files") or {}).keys()),
    }


@router.get("/checkpoints/{session}")
async def list_checkpoints(session: str) -> dict:
    _check_sid(session)
    store = _checkpoint_store(session)
    cps = [_cp_summary(c) for c in store.list()]
    return {"session": session, "count": len(cps), "items": cps}


@router.post("/checkpoints/{session}/rewind")
async def rewind_checkpoint(session: str, body: RewindBody) -> dict:
    """回滚到第 n 个检查点：按快照还原工作区文件 + 删除其后检查点（新时间线）。

    返回检查点摘要与 history（调用方据此截断会话历史展示）。
    注意：SM3 决策链只追加不回滚；Web 会话日志链（session_log）不在检查点范围内，
    需要同时截断聊天记录时请另行处理会话日志。"""
    _check_sid(session)
    store = _checkpoint_store(session)
    cp = store.get(body.n)
    if cp is None:
        raise HTTPException(status_code=404, detail="checkpoint not found")
    # 尽量还原工作区文件：按快照内 slug 定位工作区，找不到则只截断检查点时间线
    ws = None
    restored: list[str] = []
    slug = (cp.get("workspace") or {}).get("slug", "")
    if slug:
        try:
            from agent_core.workspace import get_workspace_manager

            ws = get_workspace_manager().get(slug)
        except Exception:  # noqa: BLE001 — 工作区缺失不阻断回滚
            ws = None
    cp = store.rewind(body.n, ws=ws)
    if cp is None:  # 并发下被删，兜底
        raise HTTPException(status_code=404, detail="checkpoint not found")
    if ws is not None:
        restored = sorted((cp.get("workspace") or {}).get("files", {}).keys())
    return {
        "ok": True,
        "session": session,
        "checkpoint": _cp_summary(cp),
        "restored_files": restored,
        "history": cp.get("history") or [],
        "note": "决策链（decisions.jsonl）与 Web 会话日志链不回滚，仅截断检查点时间线",
    }
