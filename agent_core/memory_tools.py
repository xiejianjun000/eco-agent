#!/usr/bin/env python3
"""
agent_core/memory_tools.py — 记忆树 + 策略热更新 标准工具集（对齐 DSH eco-memory-tree / eco-permission-gate）

把 MemoryTree 的节点管理/检索/遗忘/Obsidian 同步，以及权限策略热更新，
封装为模型可调用的标准工具（eco_memory_* / eco_policy_reload），
供聊天通道 _run_tool 与 subagent/外部调用方按注册表反查执行。
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger("eco.memory_tools")


def _mt():
    from _scripts.memory_tree import MemoryTree

    return MemoryTree()


def _j(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


def _memory_add(type: str = "case", title: str = "", content: str = "",
                tags: list | None = None, score: float = 50.0,
                parent_id: str = None, source: str = "manual",
                confidence: str = "medium") -> str:
    if not title or not content:
        return _j({"ok": False, "error": "title 与 content 必填"})
    try:
        node = _mt().create_node(type, title, content, tags=tags, score=score,
                                 parent_id=parent_id, source=source,
                                 confidence=confidence)
        return _j({"ok": True, "node": node})
    except Exception as e:  # noqa: BLE001
        return _j({"ok": False, "error": f"{type(e).__name__}: {e}"})


def _memory_update(node_id: str = "", **kw) -> str:
    if not node_id:
        return _j({"ok": False, "error": "node_id 必填"})
    try:
        node = _mt().update_node(node_id, **kw)
        return _j({"ok": node is not None, "node": node,
                   "error": "" if node is not None else "节点不存在"})
    except Exception as e:  # noqa: BLE001
        return _j({"ok": False, "error": f"{type(e).__name__}: {e}"})


def _memory_delete(node_id: str = "") -> str:
    if not node_id:
        return _j({"ok": False, "error": "node_id 必填"})
    try:
        ok = _mt().delete_node(node_id)
        return _j({"ok": ok, "error": "" if ok else "节点不存在"})
    except Exception as e:  # noqa: BLE001
        return _j({"ok": False, "error": f"{type(e).__name__}: {e}"})


def _memory_search(query: str = "", type: str = None, limit: int = 10,
                   hybrid: bool = True) -> str:
    if not query:
        return _j({"ok": False, "error": "query 必填"})
    try:
        mt = _mt()
        if hybrid:
            nodes = mt.search_hybrid(query, type=type)
        else:
            nodes = mt.search(query, type=type, max_results=limit)
        return _j({"ok": True, "count": len(nodes), "nodes": nodes[:limit]})
    except Exception as e:  # noqa: BLE001
        return _j({"ok": False, "error": f"{type(e).__name__}: {e}"})


def _memory_stats() -> str:
    try:
        return _j({"ok": True, "stats": _mt().get_stats()})
    except Exception as e:  # noqa: BLE001
        return _j({"ok": False, "error": f"{type(e).__name__}: {e}"})


def _memory_prune(min_score: float = None, max_age_days: int = None,
                  dry_run: bool = True) -> str:
    if min_score is None and max_age_days is None:
        return _j({"ok": False, "error": "min_score 或 max_age_days 至少给一项"})
    try:
        r = _mt().prune(min_score=min_score, max_age_days=max_age_days,
                        dry_run=dry_run)
        r["ok"] = True
        return _j(r)
    except Exception as e:  # noqa: BLE001
        return _j({"ok": False, "error": f"{type(e).__name__}: {e}"})


def _memory_sync(mode: str = "both", vault_path: str = None) -> str:
    """mode: to（导出到 Obsidian）/ from（从 Obsidian 导入）/ both（双向）。"""
    try:
        mt = _mt()
        if mode == "to":
            r = mt.sync_to_obsidian(vault_path=vault_path) if vault_path else mt.sync_to_obsidian()
            return _j({"ok": True, "direction": "to", "result": r})
        if mode == "from":
            r = mt.sync_from_obsidian()
            return _j({"ok": True, "direction": "from", "result": r})
        to = mt.sync_to_obsidian(vault_path=vault_path) if vault_path else mt.sync_to_obsidian()
        fr = mt.sync_from_obsidian()
        return _j({"ok": True, "direction": "both", "to": to, "from": fr})
    except Exception as e:  # noqa: BLE001
        return _j({"ok": False, "error": f"{type(e).__name__}: {e}"})


def _policy_reload() -> str:
    """热重载权限策略：重新解析 PERMISSION.md 工具风险覆盖 + L3 白名单 + glob 规则，无需重启进程。"""
    try:
        from agent_core.permissions import load_overrides, load_l3_whitelist, load_glob_rules

        overrides = load_overrides()
        whitelist = load_l3_whitelist()
        glob_rules = load_glob_rules()
        return _j({"ok": True, "overrides_count": len(overrides),
                   "l3_whitelist_count": len(whitelist),
                   "glob_rules_count": len(glob_rules),
                   "note": "PERMISSION.md tool_risk_overrides / L3 白名单 / glob 规则已重新解析生效"})
    except Exception as e:  # noqa: BLE001
        return _j({"ok": False, "error": f"{type(e).__name__}: {e}"})


def dispatch_memory_tool(name: str, arguments: dict) -> str:
    """按工具名分发到对应 handler（聊天通道 _run_tool 与 execute_tool 共用）。"""
    args = arguments or {}
    if name == "eco_memory_add":
        return _memory_add(
            type=str(args.get("type", "case")),
            title=str(args.get("title", "")),
            content=str(args.get("content", "")),
            tags=args.get("tags") if isinstance(args.get("tags"), list) else None,
            score=float(args.get("score", 50.0) or 50.0),
            parent_id=args.get("parent_id") or None,
            source=str(args.get("source", "manual")),
            confidence=str(args.get("confidence", "medium")),
        )
    if name == "eco_memory_update":
        upd = {k: v for k, v in args.items()
               if k in ("title", "content", "score", "tags", "confidence", "parent_id")}
        return _memory_update(node_id=str(args.get("node_id", "")), **upd)
    if name == "eco_memory_delete":
        return _memory_delete(node_id=str(args.get("node_id", "")))
    if name == "eco_memory_search":
        return _memory_search(
            query=str(args.get("query", "")),
            type=args.get("type") or None,
            limit=int(args.get("limit", 10) or 10),
            hybrid=bool(args.get("hybrid", True)),
        )
    if name == "eco_memory_stats":
        return _memory_stats()
    if name == "eco_memory_prune":
        return _memory_prune(
            min_score=args.get("min_score"),
            max_age_days=args.get("max_age_days"),
            dry_run=bool(args.get("dry_run", True)),
        )
    if name == "eco_memory_sync":
        return _memory_sync(mode=str(args.get("mode", "both")),
                            vault_path=args.get("vault_path") or None)
    if name == "eco_policy_reload":
        return _policy_reload()
    return _j({"ok": False, "error": f"未知工具: {name}"})
