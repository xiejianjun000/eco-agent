"""连接器「延迟工具」代理（对标 WorkBuddy connector-proxy 三段式）。

实证来源：app.asar cli/dist/codebuddy.js 符号抽取
  · 连接器工具注册为 schemed 能力，**不**进入 agent 初始工具清单；
  · ToolSearchService.describe(query)  —— 发现可用连接器工具元数据；
  · DeferExecuteTool(tool_input.toolName, …) —— 占位工具透传到真实连接器；
  · bridge.emitToolStart(…, {toolName:'DeferExecuteTool', targetToolName}) 回传前端。

为什么 eco 需要它（L1 感知，非照搬）：
  eco 已连接 14 台 MCP、约 235 个工具，但聊天清单只精选 50 个直挂（高频直调省一跳）。
  长尾（尤其腾讯文档 224 个）不在上下文里，模型既看不见也调不到。
  本模块让模型能用 tool_search 按需发现全部已连接 MCP 工具、再用 defer_execute_tool
  透传调用 —— 不必把 235 个 schema 塞进 prompt（实测 50 个已约 2 万字符）。

安全红线（零幻觉 / 风险分级）：
  defer_execute_tool 只是透传外壳，**必须对真实目标工具重跑 execute_tool 权限闸门**，
  且只读/计划模式下经 contextvar 二次拦截写工具 —— 不能因为外壳是只读就放行底层写操作。
"""

from __future__ import annotations

import contextvars
import json
import logging
import re

log = logging.getLogger(__name__)

# 当前请求是否处于只读/计划模式。chat 循环入口 set、出口 reset；
# 让 defer_execute_tool 在不增加调用链参数的情况下感知授权范围。
_readonly_ctx: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "eco_defer_readonly", default=False
)

# 写动词（与 server.api.chat._MCP_WRITE_VERBS 同口径，本地副本避免跨层导入）
_WRITE_VERBS = (
    "insert", "delete", "remove", "set_", "update", "create", "add_",
    "write", "modify", "replace", "rename", "move", "copy", "merge",
    "unmerge", "clear", "import", "export", "upload", "commit", "undo",
    "accept", "edit", "reimport", "bind", "operation", "toexcel", "toword",
)


def set_readonly(flag: bool) -> contextvars.Token:
    """进入请求时设置只读标记，返回 token 供 reset_readonly 还原。"""
    return _readonly_ctx.set(bool(flag))


def reset_readonly(token: contextvars.Token) -> None:
    _readonly_ctx.reset(token)


def _is_readonly_tool(name: str) -> bool:
    """MCP 工具按内层动词判定只读（与 chat 层一致）。"""
    if not name.startswith("mcp__"):
        return False
    tail = name.split("__", 2)[-1].lower()
    return not any(v in tail for v in _WRITE_VERBS)


def _manager():
    """取已连接的 MCP manager；未挂载则触发一次 attach（冷却内幂等）。"""
    from agent_core import tools_registry as tr

    if tr._MCP_MGR is None:
        try:
            tr.attach_mcp_tools()
        except Exception as e:  # noqa: BLE001
            log.warning("[deferred] attach MCP 失败: %s", e)
    return tr._MCP_MGR


def _all_connector_tools() -> list[dict]:
    """全部已连接连接器工具的精简元数据（去 slug 噪音，只留可发现信息）。"""
    mgr = _manager()
    if mgr is None:
        return []
    out: list[dict] = []
    seen: set[str] = set()
    for t in mgr.all_tools():
        server = t.get("server", "")
        tool = t.get("name", "")
        full = f"mcp__{server}__{tool}"
        # 与注册一致的 slug 化（defer 调用时要能反查 handler）
        from agent_core.tools_registry import normalize_tool_name

        slug = normalize_tool_name(full)
        if slug in seen:
            continue
        seen.add(slug)
        desc = re.sub(r"\s+", " ", str(t.get("description", "") or "")).strip()
        out.append({
            "server": server,
            "tool": tool,
            "call_name": slug,
            "description": desc[:200],
        })
    return out


def _score(item: dict, terms: list[str]) -> int:
    """关键词打分：工具名命中权重最高，其次描述，server 归属最低。"""
    name = item["tool"].lower()
    desc = item["description"].lower()
    srv = item["server"].lower()
    score = 0
    for t in terms:
        if not t:
            continue
        if t in name:
            score += 5
        if t in desc:
            score += 2
        if t in srv:
            score += 1
    return score


def tool_search(query: str = "", server: str = "", limit: int = 12) -> str:
    """发现可用的连接器（MCP）工具——不直接进上下文的长尾能力按需检索。

    对标 ToolSearchService.describe(query)。返回可调用工具的 call_name + 描述，
    模型拿到后用 defer_execute_tool 真正调用。
    """
    items = _all_connector_tools()
    if not items:
        return json.dumps({
            "ok": False,
            "count": 0,
            "results": [],
            "note": "当前没有已连接的 MCP 连接器，请先在「连接器」视图连接。",
        }, ensure_ascii=False)

    terms = [t for t in re.split(r"[\s,，、_./-]+", (query or "").lower()) if t]
    server_q = (server or "").strip().lower()

    scored = items
    if server_q:
        scored = [x for x in scored if server_q in x["server"].lower()]
    if terms:
        scored = [( _score(x, terms), x) for x in scored]
        scored = [(s, x) for s, x in scored if s > 0]
        scored.sort(key=lambda p: p[0], reverse=True)
        scored = [x for _, x in scored]
    # 无查询词时按 server + 工具名稳定排序，避免顺序漂移
    if not terms:
        scored = sorted(scored, key=lambda x: (x["server"], x["tool"]))

    try:
        limit = max(1, min(int(limit), 30))
    except (TypeError, ValueError):
        limit = 12

    results = [
        {
            "server": x["server"],
            "tool": x["tool"],
            "call_name": x["call_name"],
            "description": x["description"][:120],
        }
        for x in scored[:limit]
    ]
    return json.dumps({
        "ok": True,
        "count": len(results),
        "total_connected_tools": len(items),
        "results": results,
        "hint": "需要调用其中某个工具时，用 defer_execute_tool(tool_name=call_name, arguments={...}) 执行。",
    }, ensure_ascii=False)


async def defer_execute_tool(tool_name: str, arguments: dict | None = None) -> str:
    """透传执行一个连接器工具（对标 DeferExecuteTool：占位名 DeferExecuteTool，
    真实目标是 tool_input.toolName）。

    只允许调用已挂载的 mcp__* 连接器工具；对真实目标重跑权限闸门，
    只读/计划模式下额外拦截写工具。声明为 async，由 chat 循环 await（与 execute_tool 同路径）。
    """
    name = (tool_name or "").strip()
    args = arguments if isinstance(arguments, dict) else {}

    if not name.startswith("mcp__"):
        return json.dumps({
            "ok": False,
            "error": "defer_execute_tool 只能透传调用连接器工具（call_name 形如 mcp__<server>__<tool>）；"
                     "内置工具请直接调用，未发现的连接器工具请先 tool_search。",
        }, ensure_ascii=False)

    # 只读/计划模式：外壳是只读，底层写工具必须一并拦截（防代理绕过）
    if _readonly_ctx.get() and not _is_readonly_tool(name):
        return json.dumps({
            "ok": False,
            "error": f"只读/计划模式下不允许调用写工具：{name}（如需执行请退出计划模式）",
            "permission": {"decision": "deny", "reason": "readonly_mode_via_deferred_proxy"},
        }, ensure_ascii=False)

    # 确认目标确实已挂载（不存在则给可操作的引导，而非裸 not found）
    from agent_core import tools_registry as tr

    tr.attach_mcp_tools()
    resolved = tr.resolve_tool_name(name)
    if name not in tr._HANDLERS and resolved not in tr._HANDLERS:
        return json.dumps({
            "ok": False,
            "error": f"连接器工具 {name} 当前不可用（未连接或未挂载）。请先 tool_search 确认 call_name。",
        }, ensure_ascii=False)

    # 对【真实目标工具】重跑权限闸门（L1-L4 + SM3 审计），不能因代理外壳而绕过。
    import os

    if os.environ.get("ECO_PERMISSION_GATE", "1").strip().lower() not in ("0", "false", "no"):
        from agent_core.permissions import gate_tool_call, load_overrides

        allowed, level, reason = gate_tool_call(
            resolved, args, overrides=tr._merged_risk_overrides(load_overrides())
        )
        if not allowed:
            return json.dumps({
                "ok": False,
                "error": f"权限闸门拒绝 [{level}]: {reason}",
                "target_tool": resolved,
                "permission": {"level": level, "decision": "deny", "reason": reason},
            }, ensure_ascii=False)

    # 经统一分发执行（slug/原名反查、同步/异步 handler 都覆盖）
    result = await tr.execute_tool(resolved, args)

    # execute_tool 返回 JSON 字符串；包一层 target_tool，便于前端映射真实工具名
    try:
        payload = json.loads(result)
    except (TypeError, ValueError):
        payload = {"raw": result}
    return json.dumps({"ok": True, "target_tool": resolved, "result": payload}, ensure_ascii=False)


# ── 注册（幂等：重复导入不重复注册）──────────────────────────────────
_REGISTERED = False


def register_deferred_tools() -> None:
    """把两个延迟代理工具挂进工具体系（L1 只读；真实写权限由 defer 内部闸门把关）。"""
    global _REGISTERED
    if _REGISTERED:
        return
    from agent_core.tools_registry import register_external_tool

    register_external_tool(
        name="tool_search",
        description=(
            "发现可用的连接器（MCP）工具。连接器工具默认不直接进工具清单，"
            "当内置工具不够、需要某个连接器/外部系统能力（如腾讯文档建表、"
            "外部知识库、政务数据源）时，先用关键词检索，拿到 call_name 后用 "
            "defer_execute_tool 调用。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "关键词，如 腾讯文档 表格 / 法规 / 案卷"},
                "server": {"type": "string", "description": "可选，限定连接器（server）名"},
                "limit": {"type": "integer", "description": "最多返回条数（默认12，上限30）"},
            },
            "required": ["query"],
        },
        handler=tool_search,
        risk_level="L1",
        source="builtin-deferred",
    )

    register_external_tool(
        name="defer_execute_tool",
        description=(
            "透传执行一个由 tool_search 发现的连接器工具。入参 tool_name 填检索返回的 "
            "call_name（mcp__<server>__<tool>），arguments 填该工具参数。"
            "内置工具不要走这里，直接调用即可。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "tool_name": {"type": "string", "description": "tool_search 返回的 call_name"},
                "arguments": {"type": "object", "description": "目标连接器工具的参数对象"},
            },
            "required": ["tool_name"],
        },
        handler=defer_execute_tool,
        risk_level="L1",
        source="builtin-deferred",
    )
    _REGISTERED = True
    log.info("[deferred] 延迟代理工具已注册: tool_search / defer_execute_tool")
