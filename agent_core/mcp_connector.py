#!/usr/bin/env python3
"""
mcp_connector.py — Eco Agent MCP client 连接器（官方 mcp Python SDK）

把外部 MCP server 的工具动态接入 eco-agent 工具体系，与 connector_system
（D-01 连接器管理）并列互补：connector_system 管凭证/认证，本模块管
MCP 协议的工具发现与调用。

特性：
  - 支持 SSE / stdio / Streamable HTTP(http) 三种传输（官方 mcp SDK ClientSession）
  - 配置驱动：.env / 环境变量 ECO_MCP_SERVERS（JSON 数组）或代码注入
  - 连接 → list_tools → 动态注册进 ReActPlusPlus 工具体系 → call_tool
  - 统一错误处理与超时（默认 30s）
  - 断线重连（调用失败自动重连重试一次）与优雅降级：
    MCP 不可用时 register_into_react 跳过该 server，Agent 仍可跑规则模式

配置示例（.env，单行 JSON）：
  ECO_MCP_SERVERS=[
    {"name":"ehs_kb","transport":"sse","url":"http://111.230.89.107:8000/sse/"},
    {"name":"govmcp","transport":"stdio","command":["python","/path/to/run_mcp_stdio.py"]},
    {"name":"tencent_docs","transport":"http","url":"https://docs.qq.com/openapi/mcp",
     "headers":{"Authorization":"<个人Token>"}}
  ]
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("mcp_connector")

DEFAULT_TIMEOUT = 30.0  # 秒，统一超时红线

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.sse import sse_client
    from mcp.client.stdio import stdio_client
    from mcp.client.streamable_http import streamablehttp_client

    MCP_AVAILABLE = True
except Exception:  # pragma: no cover - mcp 未安装时优雅降级
    MCP_AVAILABLE = False


# ═══════════════════════════════════
# 配置
# ═══════════════════════════════════


@dataclass
class MCPServerConfig:
    """MCP server 声明"""

    name: str
    transport: str  # "sse" | "stdio" | "http"(Streamable HTTP)
    url: str = ""  # sse/http 传输必填
    command: list[str] = field(default_factory=list)  # stdio 传输必填
    env: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)  # SSE/HTTP 自定义请求头（如 X-API-Key / Authorization 鉴权）
    timeout: float = DEFAULT_TIMEOUT

    @classmethod
    def from_dict(cls, d: dict) -> MCPServerConfig:
        return cls(
            name=d["name"],
            transport=d.get("transport", "sse"),
            url=d.get("url", ""),
            command=list(d.get("command", [])),
            env=dict(d.get("env", {})),
            headers=dict(d.get("headers", {})),
            timeout=float(d.get("timeout", DEFAULT_TIMEOUT)),
        )


def load_configs_from_env(env_var: str = "ECO_MCP_SERVERS") -> list[MCPServerConfig]:
    """从环境变量 / ~/.eco/.env 加载 MCP server 配置（JSON 数组），解析失败返回空列表"""
    raw = os.environ.get(env_var, "").strip()
    if not raw:
        # 环境变量未设：回退读 ~/.eco/.env（与 llm_client 配置来源一致）
        from pathlib import Path

        env_file = Path.home() / ".eco" / ".env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    if k.strip() == env_var:
                        raw = v.strip()
                        break
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return [MCPServerConfig.from_dict(d) for d in data]
    except Exception as e:
        logger.warning(f"[MCP] {env_var} 解析失败: {e}")
        return []


def load_configs_from_registry(store=None) -> list[MCPServerConfig]:
    """从 MCP 注册表加载 server 配置（registry 源，覆盖 env 同名项）。

    store: 注册表 json 路径；默认读 ECO_MCP_REGISTRY 环境变量，
    未设置则回退 ~/.eco/mcp_servers.json。注册表缺失/损坏时返回空列表。
    """
    from agent_core.mcp_registry import MCPRegistry

    try:
        reg = MCPRegistry(store=store if store is not None else os.environ.get("ECO_MCP_REGISTRY"))
        return [MCPServerConfig.from_dict(d) for d in reg.env_configs()]
    except Exception as e:  # noqa: BLE001 — 注册表异常降级为空源
        logger.warning(f"[MCP] registry 加载失败: {e}")
        return []


def load_merged_configs() -> list[MCPServerConfig]:
    """env 与 registry 双源合并配置：同名 registry 覆盖 env，注册表缺失自动降级。"""
    merged: dict[str, MCPServerConfig] = {}
    for cfg in load_configs_from_env():
        merged[cfg.name] = cfg
    for cfg in load_configs_from_registry():
        merged[cfg.name] = cfg
    return list(merged.values())


# ═══════════════════════════════════
# 单个 server 连接（持有 session，跑在后台事件循环）
# ═══════════════════════════════════


class MCPServerConnection:
    """一个 MCP server 的持久连接（异步上下文在专属事件循环线程中托管）"""

    def __init__(self, config: MCPServerConfig, loop: asyncio.AbstractEventLoop):
        self.config = config
        self._loop = loop
        self._session = None
        self._cm_stack: list = []  # 传输 / session 的 async context managers
        self.tools: list[dict] = []
        self.connected = False
        self.last_error = ""

    # ---- 异步核心（在 self._loop 内执行）----

    async def _connect_async(self) -> None:
        if not MCP_AVAILABLE:
            raise RuntimeError("官方 mcp SDK 未安装（pip install mcp）")
        cfg = self.config
        if cfg.transport == "sse":
            cm = sse_client(cfg.url, headers=cfg.headers or None)
        elif cfg.transport == "http":
            # Streamable HTTP（MCP 官方传输，如腾讯文档 openapi/mcp 端点）
            cm = streamablehttp_client(cfg.url, headers=cfg.headers or None)
        elif cfg.transport == "stdio":
            env = dict(os.environ)
            env.update(cfg.env)
            params = StdioServerParameters(command=cfg.command[0], args=cfg.command[1:], env=env)
            cm = stdio_client(params)
        else:
            raise ValueError(f"不支持的传输类型: {cfg.transport}")

        entered = await cm.__aenter__()
        if isinstance(entered, tuple) and len(entered) == 3:
            # Streamable HTTP 传输返回 (read, write, get_session_id)
            read, write, _get_session = entered
        else:
            read, write = entered
        self._cm_stack.append(cm)
        session = ClientSession(read, write)
        await session.__aenter__()
        # 输出校验降级：远程服务的输出 schema 与真实返回常不一致
        # （如腾讯文档 manage.search_file 声明 modify_time 为 integer 实返字符串），
        # mcp SDK 客户端强校验会 RuntimeError 拒收真实数据。
        # 校验仅具格式严格性价值、不承载安全边界——改为告警不阻断。
        if hasattr(session, "_validate_tool_result"):
            _orig_validate = ClientSession._validate_tool_result

            async def _lenient_validate(name, result):
                try:
                    await _orig_validate(session, name, result)
                except Exception as e:  # noqa: BLE001 — 格式不严 ≠ 数据不可用
                    logger.warning("[mcp_connector] %s 输出校验未通过（降级放行）: %s", name, str(e)[:140])

            session._validate_tool_result = _lenient_validate
        self._cm_stack.append(session)
        await asyncio.wait_for(session.initialize(), timeout=cfg.timeout)
        result = await asyncio.wait_for(session.list_tools(), timeout=cfg.timeout)
        self.tools = [
            {"name": t.name, "description": t.description or "", "inputSchema": getattr(t, "inputSchema", {}) or {}}
            for t in result.tools
        ]
        self._session = session
        self.connected = True
        self.last_error = ""

    async def _disconnect_async(self) -> None:
        while self._cm_stack:
            cm = self._cm_stack.pop()
            try:
                await cm.__aexit__(None, None, None)
            except Exception:
                pass
        self._session = None
        self.connected = False

    async def _call_async(self, tool: str, arguments: dict) -> Any:
        return await asyncio.wait_for(
            self._session.call_tool(tool, arguments),
            timeout=self.config.timeout,
        )

    # ---- 同步 façade（线程安全提交到后台事件循环）----

    def _run(self, coro, timeout: float | None = None):
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return fut.result(timeout or (self.config.timeout + 10))

    def connect(self) -> bool:
        """连接并 list_tools；失败返回 False（优雅降级，不抛异常）"""
        try:
            self._run(self._connect_async())
            logger.info(f"[MCP] {self.config.name}: 已连接，发现 {len(self.tools)} 个工具")
            return True
        except Exception as e:
            self.connected = False
            self.last_error = str(e)
            logger.warning(f"[MCP] {self.config.name}: 连接失败（降级跳过）: {e}")
            return False

    def disconnect(self) -> None:
        try:
            self._run(self._disconnect_async(), timeout=10)
        except Exception:
            pass

    def reconnect(self) -> bool:
        self.disconnect()
        return self.connect()

    def call_tool(self, tool: str, arguments: dict) -> dict:
        """
        调用远程工具，统一返回 {"success", "text", "is_error", "elapsed_ms", ...}。
        连接类错误自动重连重试一次；超时/协议错误走统一错误处理。
        """
        if not self.connected or self._session is None:
            # 先尝试重连再放弃 —— 远程服务器会掉线，掉线后 connected 置 False，
            # 此处若直接返回，这台在本进程内就再也不可用了，哪怕对方几秒后恢复。
            # 实测事故：permit-remote 启动时正常发现 12 个工具，调用时已掉线，
            # 只回一句 "server 未连接"，模型看不出是掉线，
            # 编成「L3 权限未开放，需要运维加白名单」—— 完全不存在的制度理由，
            # 而那台服务器本就在只读白名单里、工具算出来是 L1。
            logger.info(f"[MCP] {self.config.name} 未连接，尝试重连后再调用 {tool}")
            if not self.reconnect():
                return {
                    "success": False,
                    "error": f"远程服务当前不可用（重连失败）: {self.config.name}",
                    "failure": "unreachable",
                    "hint": "远程 MCP 服务器掉线或网络不通，与权限、白名单无关；稍后重试。",
                    "server": self.config.name,
                    "tool": tool,
                }

        start = time.time()
        last_exc: Exception | None = None
        for attempt in (1, 2):
            try:
                result = self._run(self._call_async(tool, arguments), timeout=self.config.timeout + 5)
                text = "\n".join(getattr(c, "text", "") for c in (result.content or []) if getattr(c, "type", "") == "text")
                is_error = bool(getattr(result, "isError", False))
                return {
                    "success": not is_error,
                    "is_error": is_error,
                    "text": text,
                    "server": self.config.name,
                    "tool": tool,
                    "elapsed_ms": int((time.time() - start) * 1000),
                }
            except Exception as e:
                # 工具级错误（服务端 JSON-RPC error，如"未找到法规"）不是连接故障：
                # 直接返回失败，不重连不重试——重连只会把同一条诚实错误放大成两次
                if type(e).__name__ in ("McpError", "MCPError"):
                    return {
                        "success": False,
                        "error": str(e),
                        "server": self.config.name,
                        "tool": tool,
                        "elapsed_ms": int((time.time() - start) * 1000),
                    }
                last_exc = e
                logger.warning(f"[MCP] {self.config.name}.{tool} 第{attempt}次调用失败: {e}")
                if attempt == 1:
                    # 断线重连后重试一次
                    if not self.reconnect():
                        break
        # 错误串要让模型看得懂。ClosedResourceError 的 str() 是空的，
        # 拼出来就是 "ClosedResourceError: " —— 模型无从判断这是连接问题，
        # 于是编了个「L3 权限未开放」的理由。这里显式分类并带上处置提示。
        _name = type(last_exc).__name__
        _msg = str(last_exc).strip()
        _conn_errs = ("ClosedResourceError", "ConnectionError", "BrokenResourceError",
                      "IncompleteRead", "RemoteProtocolError")
        if _name in _conn_errs or "closed" in _msg.lower():
            _failure, _hint = "unreachable", (
                "远程 MCP 服务器连接已断开（服务端掉线或网络中断），"
                "与权限、白名单无关；稍后重试。"
            )
            _err = f"远程服务连接中断（{_name}）: {self.config.name}"
        elif isinstance(last_exc, TimeoutError) or "timeout" in _msg.lower():
            _failure, _hint = "timeout", "远程服务响应超时，可稍后重试或缩小查询范围。"
            _err = f"远程服务超时（{_name}）: {self.config.name}"
        else:
            _failure, _hint = "error", "远程服务返回错误，请核对参数名与取值。"
            _err = f"{_name}: {_msg}" if _msg else f"{_name}（无错误详情）"
        return {
            "success": False,
            "error": _err,
            "failure": _failure,
            "hint": _hint,
            "server": self.config.name,
            "tool": tool,
            "elapsed_ms": int((time.time() - start) * 1000),
        }


# ═══════════════════════════════════
# 连接器管理器（对接 eco-agent 工具体系）
# ═══════════════════════════════════


class MCPConnectorManager:
    """
    MCP 连接器管理器——所有 server 共用一个后台事件循环线程。

    用法:
        mgr = MCPConnectorManager(configs)
        mgr.connect_all()                 # 不可用的 server 自动降级跳过
        mgr.register_into_react(react)    # 动态注册 mcp__{server}__{tool}
        result = mgr.call_tool("govmcp", "query_air_quality", {"region": "娄底"})
        mgr.close()
    """

    def __init__(self, configs: list[MCPServerConfig] | None = None):
        self.configs = configs if configs is not None else load_merged_configs()
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, name="mcp-connector-loop", daemon=True)
        self._thread.start()
        self._servers: dict[str, MCPServerConnection] = {}

    # ---- 连接管理 ----

    def connect_all(self, timeout: float = 120.0) -> dict[str, bool]:
        """并发连接全部 server（慢服务不再串行拖累整体；各自超时降级）。"""
        status: dict[str, bool] = {}
        conns: dict[str, MCPServerConnection] = {}
        for cfg in self.configs:
            conn = MCPServerConnection(cfg, self._loop)
            self._servers[cfg.name] = conn
            conns[cfg.name] = conn

        async def _safe_connect(conn: MCPServerConnection) -> None:
            try:
                await asyncio.wait_for(conn._connect_async(), timeout=conn.config.timeout + 10)
                logger.info(f"[MCP] {conn.config.name}: 已连接，发现 {len(conn.tools)} 个工具")
            except Exception as e:  # noqa: BLE001 — 单服务失败降级跳过
                conn.connected = False
                conn.last_error = str(e)
                logger.warning(f"[MCP] {conn.config.name}: 连接失败（降级跳过）: {e}")

        async def _gather() -> None:
            await asyncio.gather(*(_safe_connect(c) for c in conns.values()))

        try:
            asyncio.run_coroutine_threadsafe(_gather(), self._loop).result(timeout)
        except Exception:  # noqa: BLE001 — 全局超时也不阻断
            pass
        for name, conn in conns.items():
            status[name] = conn.connected
        return status

    def get(self, name: str) -> MCPServerConnection | None:
        return self._servers.get(name)

    def health_check(self, timeout: float = 45.0) -> dict[str, bool]:
        """巡检所有已知 server，对掉线的并发重连一次。返回巡检后的连通状态。

        远程 MCP（尤其 111.230.89.107 那批）会不定时掉线。没有巡检时，
        一台服务器掉线后要等到下次有人调用它才会被发现，而那次调用本身就失败了 ——
        用户看到的是「查不到」，模型看到的是一个空消息的 ClosedResourceError，
        实测被编成了「L3 权限未开放，需要运维加白名单」。

        必须并发：实测 9 台不可达时串行重连跑满 5 分钟仍未返回
        （每台十几秒超时 × 9）。connect_all 早就是并发的，这里对齐它的做法，
        并加总时限兜底 —— 巡检超时只意味着这一轮没修完，下一轮继续。
        """
        result: dict[str, bool] = {}
        down = []
        for name, conn in list(self._servers.items()):
            if conn.connected:
                result[name] = True
            else:
                down.append((name, conn))
        if not down:
            return result

        async def _try(name: str, conn: MCPServerConnection) -> tuple[str, bool]:
            try:
                await asyncio.wait_for(conn._connect_async(), timeout=conn.config.timeout + 5)
                logger.info(f"[MCP健康检查] {name}: 已自动恢复，{len(conn.tools)} 个工具")
                return name, True
            except Exception as e:  # noqa: BLE001 单台失败不影响其余
                conn.connected = False
                conn.last_error = str(e)
                logger.warning(f"[MCP健康检查] {name}: 仍不可达")
                return name, False

        async def _all() -> list:
            return await asyncio.gather(*(_try(n, c) for n, c in down),
                                        return_exceptions=True)

        try:
            # 管理器没有 _run（那是单个连接的方法），用 connect_all 同款做法：
            # 把协程投到共享后台事件循环上跑
            for item in asyncio.run_coroutine_threadsafe(_all(), self._loop).result(timeout) or []:
                if isinstance(item, tuple):
                    result[item[0]] = item[1]
        except Exception as e:  # noqa: BLE001 整轮超时：本轮没修完，下轮继续
            logger.warning(f"[MCP健康检查] 本轮未完成（{e}），下轮继续")
        for name, _ in down:
            result.setdefault(name, False)
        return result

    def available(self, name: str) -> bool:
        conn = self._servers.get(name)
        return bool(conn and conn.connected)

    def list_tools(self, name: str) -> list[dict]:
        conn = self._servers.get(name)
        return list(conn.tools) if conn else []

    def all_tools(self) -> list[dict]:
        """全部已连接 server 的工具，带 server 归属"""
        out = []
        for name, conn in self._servers.items():
            for t in conn.tools:
                out.append({"server": name, **t})
        return out

    def call_tool(self, server: str, tool: str, arguments: dict) -> dict:
        conn = self._servers.get(server)
        if conn is None:
            return {"success": False, "error": f"未知 MCP server: {server}"}
        return conn.call_tool(tool, arguments)

    # ---- 对接 ReActPlusPlus 工具体系 ----

    def register_into_react(self, react, prefix: str = "mcp") -> list[str]:
        """
        把全部已连接 server 的远程工具注册进 ReActPlusPlus：
        工具名 mcp__{server}__{tool}；不可用的 server 跳过（规则模式照常）。
        返回已注册工具名列表。
        """
        registered = []
        for name, conn in self._servers.items():
            if not conn.connected:
                continue
            for t in conn.tools:
                full_name = f"{prefix}__{name}__{t['name']}"

                def make_handler(srv=name, tool=t["name"]):
                    def handler(**kwargs) -> dict:
                        return self.call_tool(srv, tool, kwargs)

                    return handler

                react.register_tool(
                    full_name,
                    make_handler(),
                    description=f"[MCP:{name}] {t['description']}",
                )
                registered.append(full_name)
        logger.info(f"[MCP] 已注册 {len(registered)} 个远程工具进 ReAct 工具体系")
        return registered

    # ---- 收尾 ----

    def close(self) -> None:
        for conn in self._servers.values():
            conn.disconnect()
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
