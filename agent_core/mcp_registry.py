#!/usr/bin/env python3
"""
mcp_registry.py — MCP 管理面注册表（对标路线 P0-3，对标 Hermes MCP Command Center）

对标功能：
  - 拖入导入  -> add() 持久化 server 配置（~/.eco/mcp_servers.json）
  - 健康检查  -> health() 真实连接 + list_tools，记录 ok/tools/latency_ms
  - 用量      -> call() 计数（usage_count / last_used_at / by_tool）

与 mcp_connector.py 分工：connector 管"连接/调用"协议细节；本模块管
"清单/状态/用量"治理面。ConnectorManager 仍从 ECO_MCP_SERVERS 环境变量
读取存量配置，本模块读取的注册表可在 add 时同步追加进环境（供 react 接线）。

零第三方依赖（json + time）。
"""

import json
import os
import time
from pathlib import Path

DEFAULT_STORE = Path(os.environ.get("ECO_MCP_REGISTRY", "~/.eco/mcp_servers.json")).expanduser()


def _atomic_write(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


class MCPRegistry:
    """MCP server 清单治理面：导入/移除/健康/用量。"""

    def __init__(self, store: Path | str | None = None):
        self.store = Path(store) if store else DEFAULT_STORE
        if not self.store.exists():
            _atomic_write(self.store, {"servers": {}})

    def _read(self) -> dict:
        return json.loads(self.store.read_text(encoding="utf-8"))

    def _write(self, data: dict) -> None:
        _atomic_write(self.store, data)

    # ── 导入（对标拖入导入）─────────────────────────────────
    def add(
        self,
        name: str,
        transport: str,
        *,
        url: str | None = None,
        command: list[str] | None = None,
        headers: dict | None = None,
    ) -> dict:
        """登记一个外部 MCP server。

        transport: sse / http / stdio
        - sse/http 需要 url（stdio 无需）
        - stdio 需要 command（如 ["python", "/path/run.py"]）
        """
        name = (name or "").strip()
        if not name:
            raise ValueError("name is required")
        transport = (transport or "http").lower()
        if transport in ("sse", "http") and not url:
            raise ValueError(f"transport={transport} requires url")
        if transport == "stdio" and not command:
            raise ValueError("transport=stdio requires command")
        cfg = {"name": name, "transport": transport}
        if url:
            cfg["url"] = url
        if command:
            cfg["command"] = command
        if headers:
            cfg["headers"] = headers
        data = self._read()
        prev = data["servers"].get(name, {})
        entry = {
            "config": cfg,
            "added_at": prev.get("added_at") or time.strftime("%Y-%m-%dT%H:%M:%S"),
            "health": prev.get("health", {"ok": None, "last_check": None, "tools": [], "latency_ms": None}),
            "usage": prev.get("usage", {"call_count": 0, "last_used_at": None, "by_tool": {}}),
        }
        data["servers"][name] = entry
        self._write(data)
        return entry

    def remove(self, name: str) -> bool:
        data = self._read()
        if name in data["servers"]:
            del data["servers"][name]
            self._write(data)
            return True
        return False

    def list(self) -> list[dict]:
        data = self._read()
        out = []
        for name, e in sorted(data["servers"].items()):
            h = e.get("health", {})
            u = e.get("usage", {})
            out.append(
                {
                    "name": name,
                    "transport": e["config"].get("transport"),
                    "url": e["config"].get("url", ""),
                    "ok": h.get("ok"),
                    "tools": len(h.get("tools", [])),
                    "last_check": h.get("last_check"),
                    "call_count": u.get("call_count", 0),
                }
            )
        return out

    def get(self, name: str) -> dict | None:
        return self._read()["servers"].get(name)

    def env_configs(self) -> "list[dict]":
        """把注册表 config 转成 mcp_connector 的 MCPServerConfig 可读 dict。"""
        return [e["config"] for e in self._read()["servers"].values()]

    # ── 健康检查（对标 Command Center healthcheck）──────────
    def health(self, name: str | None = None) -> dict:
        """真实连接目标 server 并 list_tools，回写注册表健康状态。

        使用 mcp_connector.MCPConnectorManager 执行（同款协议细节）。
        """
        from agent_core.mcp_connector import MCPConnectorManager, MCPServerConfig

        names = [name] if name else [e["name"] for e in self.list()]
        if not names:
            return {"ok": False, "detail": "registry empty"}
        results = {}
        for n in names:
            entry = self.get(n)
            if entry is None:
                results[n] = {"ok": False, "detail": "not found"}
                continue
            try:
                cfg = MCPServerConfig.from_dict(entry["config"])
                mgr = MCPConnectorManager([cfg])
                t0 = time.time()
                conns = mgr.connect_all(timeout=60.0)
                ok = bool(conns.get(n))
                tools = mgr.list_tools(n) if ok else []
                latency_ms = int((time.time() - t0) * 1000)
                mgr.close()
                status = {
                    "ok": ok,
                    "last_check": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "tools": [t.get("name") for t in tools][:200],
                    "latency_ms": latency_ms,
                    "detail": None if ok else "connect failed",
                }
            except Exception as e:  # noqa: BLE001
                status = {
                    "ok": False,
                    "last_check": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "tools": [],
                    "latency_ms": None,
                    "detail": str(e)[:200],
                }
            self._update_health(n, status)
            results[n] = {k: v for k, v in status.items() if k != "tools"}
            results[n]["tool_count"] = len(status["tools"])
            results[n]["tool_names"] = status["tools"][:15]
        return {"ok": all(r["ok"] for r in results.values()), "results": results}

    def _update_health(self, name: str, status: dict) -> None:
        data = self._read()
        if name in data["servers"]:
            data["servers"][name]["health"] = status
            self._write(data)

    # ── 用量（对标 Command Center usage）────────────────────
    def record_call(self, name: str, tool: str) -> None:
        data = self._read()
        e = data["servers"].get(name)
        if e is None:
            return
        u = e.setdefault("usage", {"call_count": 0, "last_used_at": None, "by_tool": {}})
        u["call_count"] = int(u.get("call_count", 0)) + 1
        u["last_used_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        by_tool = u.setdefault("by_tool", {})
        by_tool[tool] = int(by_tool.get(tool, 0)) + 1
        self._write(data)

    def usage(self, name: str | None = None) -> dict:
        data = self._read()
        if name:
            e = data["servers"].get(name)
            return {"name": name, "usage": e.get("usage", {}) if e else {}}
        return {"servers": {n: e.get("usage", {}) for n, e in data["servers"].items()}}
