#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MCP-over-SSE 持久会话客户端（单连接复用，已验证可对接 ehs-kb-ops）。

关键：一条 SSE 连接完成 initialize 后，在其上连续发起多个 tools/call，
避免服务端"快速多连接时响应路由到旧连接"的问题。

用法（作为模块）：
    from mcp_session import MCPClient
    c = MCPClient("http://host:8000/sse/", "APIKEY")
    c.connect()
    print(c.search("在线监测 不正常运行", top_k=6))
    c.close()

命令行：
    python3 mcp_session.py <sse_url> <api_key> <query1> [query2 ...]
"""
import sys
import json
import time
import threading
import urllib.request
import urllib.error
import urllib.parse

PROTOCOL = "2024-11-05"
TIMEOUT = 30.0


class MCPClient:
    def __init__(self, sse_url, api_key):
        self.sse_url = sse_url.rstrip("/") + "/"
        self.api_key = api_key
        self.pending = {}
        self.pending_lock = threading.Lock()
        self.session = {"messages_url": None}
        self.stop = threading.Event()
        self._rid = 100
        self._reader = None

    def _parse_block(self, lines):
        ev, data = None, []
        for line in lines:
            if line.startswith("event:"):
                ev = line[6:].strip()
            elif line.startswith("data:"):
                data.append(line[5:].strip())
        return ev, "\n".join(data)

    def _reader_loop(self):
        req = urllib.request.Request(
            self.sse_url,
            headers={"X-API-Key": self.api_key, "Accept": "text/event-stream"},
        )
        try:
            resp = urllib.request.urlopen(req, timeout=120)
        except Exception as e:
            print(f"[reader] SSE 连接失败: {e}", file=sys.stderr)
            return
        buf = []
        try:
            for raw in resp:
                if self.stop.is_set():
                    break
                line = raw.decode("utf-8", "replace").rstrip("\n").rstrip("\r")
                if line == "":
                    if buf:
                        ev, data = self._parse_block(buf)
                        buf = []
                        if ev == "endpoint":
                            self.session["messages_url"] = urllib.parse.urljoin(self.sse_url, data)
                        elif ev == "message" and data:
                            try:
                                msg = json.loads(data)
                            except Exception:
                                continue
                            mid = msg.get("id")
                            if mid is not None:
                                with self.pending_lock:
                                    if mid in self.pending:
                                        self.pending[mid]["result"] = msg
                                        self.pending[mid]["event"].set()
                    else:
                        buf = []
                else:
                    buf.append(line)
        except Exception as e:
            if not self.stop.is_set():
                print(f"[reader] SSE 读取异常: {e}", file=sys.stderr)

    def connect(self):
        self._reader = threading.Thread(target=self._reader_loop, daemon=True)
        self._reader.start()
        deadline = time.time() + TIMEOUT
        while self.session["messages_url"] is None and time.time() < deadline:
            time.sleep(0.05)
        if self.session["messages_url"] is None:
            self.stop.set()
            raise RuntimeError("未收到 SSE endpoint 事件")
        init = self._rpc("initialize", {
            "protocolVersion": PROTOCOL,
            "capabilities": {},
            "clientInfo": {"name": "qclaw-sse-session", "version": "1.0"},
        })
        self._rpc("notifications/initialized", wait=False)
        return init["result"]["serverInfo"]

    def _rpc(self, method, params=None, wait=True):
        self._rid += 1
        rid = self._rid
        payload = {"jsonrpc": "2.0", "id": rid, "method": method}
        if params is not None:
            payload["params"] = params
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.session["messages_url"],
            data=data,
            headers={
                "X-API-Key": self.api_key,
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
            method="POST",
        )
        if not wait:
            urllib.request.urlopen(req, timeout=TIMEOUT)
            return None
        with self.pending_lock:
            self.pending[rid] = {"event": threading.Event(), "result": None}
        urllib.request.urlopen(req, timeout=TIMEOUT)
        ok = self.pending[rid]["event"].wait(TIMEOUT)
        with self.pending_lock:
            res = self.pending.pop(rid, {}).get("result")
        if not ok:
            raise TimeoutError(f"调用 {method} 超时")
        return res

    def call_tool(self, name, arguments=None):
        res = self._rpc("tools/call", {"name": name, "arguments": arguments or {}})
        return res["result"]["content"][0]["text"]

    def search(self, query, top_k=6):
        return self.call_tool("kb_search", {"query": query, "top_k": top_k})

    def list_tools(self):
        res = self._rpc("tools/list")
        return res["result"]["tools"]

    def close(self):
        self.stop.set()


def main():
    if len(sys.argv) < 4:
        print("用法: python3 mcp_session.py <sse_url> <api_key> <query1> [query2 ...]")
        sys.exit(1)
    c = MCPClient(sys.argv[1], sys.argv[2])
    c.connect()
    try:
        for q in sys.argv[3:]:
            print("=" * 70)
            print(f"# {q}")
            print("=" * 70)
            try:
                print(c.search(q, top_k=6))
            except Exception as e:
                print(f"[失败] {e}")
            print("")
    finally:
        c.close()


if __name__ == "__main__":
    main()
