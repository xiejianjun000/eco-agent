#!/usr/bin/env python3
"""
mcp_connector.py — Eco Agent MCP client 连接器（官方 mcp Python SDK）

把外部 MCP server 的工具动态接入 eco-agent 工具体系，与 connector_system
（D-01 连接器管理）并列互补：connector_system 管凭证/认证，本模块管
MCP 协议的工具发现与调用。

特性：
  - 支持 SSE 与 stdio 两种传输（官方 mcp SDK ClientSession）
  - 配置驱动：.env / 环境变量 ECO_MCP_SERVERS（JSON 数组）或代码注入
  - 连接 → list_tools → 动态注册进 ReActPlusPlus 工具体系 → call_tool
  - 统一错误处理与超时（默认 30s）
  - 断线重连（调用失败自动重连重试一次）与优雅降级：
    MCP 不可用时 register_into_react 跳过该 server，Agent 仍可跑规则模式

配置示例（.env，单行 JSON）：
  ECO_MCP_SERVERS=[
    {"name":"ehs_kb","transport":"sse","url":"http://111.230.89.107:8000/sse/"},
    {"name":"govmcp","transport":"stdio","command":["python","/path/to/run_mcp_stdio.py"]}
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
from typing import Any, Callable

logger = logging.getLogger("mcp_connector")

DEFAULT_TIMEOUT = 30.0  # 秒，统一超时红线

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.sse import sse_client
    from mcp.client.stdio import stdio_client
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
    transport: str                      # "sse" | "stdio"
    url: str = ""                       # sse 传输必填
    command: list[str] = field(default_factory=list)  # stdio 传输必填
    env: dict[str, str] = field(default_factory=dict)
    timeout: float = DEFAULT_TIMEOUT

    @classmethod
    def from_dict(cls, d: dict) -> "MCPServerConfig":
        return cls(
            name=d["name"],
            transport=d.get("transport", "sse"),
            url=d.get("url", ""),
            command=list(d.get("command", [])),
            env=dict(d.get("env", {})),
            timeout=float(d.get("timeout", DEFAULT_TIMEOUT)),
        )


def load_configs_from_env(env_var: str = "ECO_MCP_SERVERS") -> list[MCPServerConfig]:
    """从环境变量 / .env 加载 MCP server 配置（JSON 数组），解析失败返回空列表"""
    raw = os.environ.get(env_var, "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return [MCPServerConfig.from_dict(d) for d in data]
    except Exception as e:
        logger.warning(f"[MCP] {env_var} 解析失败: {e}")
        return []


# ═══════════════════════════════════
# 单个 server 连接（持有 session，跑在后台事件循环）
# ═══════════════════════════════════

class MCPServerConnection:
    """一个 MCP server 的持久连接（异步上下文在专属事件循环线程中托管）"""

    def __init__(self, config: MCPServerConfig, loop: asyncio.AbstractEventLoop):
        self.config = config
        self._loop = loop
        self._session = None
        self._cm_stack: list = []   # 传输 / session 的 async context managers
        self.tools: list[dict] = []
        self.connected = False
        self.last_error = ""

    # ---- 异步核心（在 self._loop 内执行）----

    async def _connect_async(self) -> None:
        if not MCP_AVAILABLE:
            raise RuntimeError("官方 mcp SDK 未安装（pip install mcp）")
        cfg = self.config
        if cfg.transport == "sse":
            cm = sse_client(cfg.url)
        elif cfg.transport == "stdio":
            env = dict(os.environ)
            env.update(cfg.env)
            params = StdioServerParameters(command=cfg.command[0],
                                           args=cfg.command[1:], env=env)
            cm = stdio_client(params)
        else:
            raise ValueError(f"不支持的传输类型: {cfg.transport}")

        read, write = await cm.__aenter__()
        self._cm_stack.append(cm)
        session = ClientSession(read, write)
        await session.__aenter__()
        self._cm_stack.append(session)
        await asyncio.wait_for(session.initialize(), timeout=cfg.timeout)
        result = await asyncio.wait_for(session.list_tools(), timeout=cfg.timeout)
        self.tools = [
            {"name": t.name,
             "description": t.description or "",
             "inputSchema": getattr(t, "inputSchema", {}) or {}}
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
            return {"success": False, "error": f"server 未连接: {self.config.name}"}

        start = time.time()
        last_exc: Exception | None = None
        for attempt in (1, 2):
            try:
                result = self._run(self._call_async(tool, arguments),
                                   timeout=self.config.timeout + 5)
                text = "\n".join(
                    getattr(c, "text", "") for c in (result.content or [])
                    if getattr(c, "type", "") == "text"
                )
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
                last_exc = e
                logger.warning(f"[MCP] {self.config.name}.{tool} 第{attempt}次调用失败: {e}")
                if attempt == 1:
                    # 断线重连后重试一次
                    if not self.reconnect():
                        break
        return {
            "success": False,
            "error": f"{type(last_exc).__name__}: {last_exc}",
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
        self.configs = configs if configs is not None else load_configs_from_env()
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever,
                                        name="mcp-connector-loop", daemon=True)
        self._thread.start()
        self._servers: dict[str, MCPServerConnection] = {}

    # ---- 连接管理 ----

    def connect_all(self) -> dict[str, bool]:
        """连接全部配置的 server，返回 {name: 是否成功}；失败仅记录不抛出"""
        status = {}
        for cfg in self.configs:
            conn = MCPServerConnection(cfg, self._loop)
            self._servers[cfg.name] = conn
            status[cfg.name] = conn.connect()
        return status

    def get(self, name: str) -> MCPServerConnection | None:
        return self._servers.get(name)

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
