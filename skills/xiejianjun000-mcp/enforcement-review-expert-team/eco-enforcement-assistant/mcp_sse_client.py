#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MCP-over-SSE 客户端封装（单连接模式，已验证可对接 ehs-kb-ops 服务）。

工作方式：
  1. GET <sse_url> 打开一条常驻 SSE 流，读取首条 endpoint 事件拿到 messages URL + session_id
  2. 后台线程持续读取 SSE 流上的 message 事件，按 JSON-RPC id 归位
  3. 主线程依次完成 initialize -> notifications/initialized -> tools/call
  4. 打印工具返回结果

用法：
  python3 mcp_sse_client.py <sse_url> <api_key> <tool> [json_args]
  python3 mcp_sse_client.py <sse_url> <api_key> --list        # 列出工具
  python3 mcp_sse_client.py <sse_url> <api_key> --status      # 调用 kb_status（无参）

示例：
  python3 mcp_sse_client.py http://111.230.89.107:8000/sse/ KEY kb_search '{"query":"危废","top_k":3}'
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

pending = {}          # id -> threading.Event + result
pending_lock = threading.Lock()
sse_session = {"endpoint": None, "messages_url": None, "session_id": None}
stop_event = threading.Event()


def parse_sse_block(lines):
    """把一组 SSE 行解析为 (event, data)。"""
    ev, data = None, []
    for line in lines:
        if line.startswith("event:"):
            ev = line[len("event:"):].strip()
        elif line.startswith("data:"):
            data.append(line[len("data:"):].strip())
    return ev, "\n".join(data)


def sse_reader(url, api_key):
    """后台线程：持续读取 SSE 流并归位 message 事件。"""
    req = urllib.request.Request(url, headers={"X-API-Key": api_key, "Accept": "text/event-stream"})
    try:
        resp = urllib.request.urlopen(req, timeout=120)
    except Exception as e:
        print(f"[reader] SSE 连接失败: {e}", file=sys.stderr)
        return
    buf = []
    try:
        for raw in resp:
            if stop_event.is_set():
                break
            line = raw.decode("utf-8", "replace").rstrip("\n").rstrip("\r")
            if line == "":
                if buf:
                    ev, data = parse_sse_block(buf)
                    buf = []
                    if ev == "endpoint":
                        sse_session["endpoint"] = data
                        # endpoint 为相对路径（如 /sse/messages/?session_id=xxx），需解析为绝对 URL
                        sse_session["messages_url"] = urllib.parse.urljoin(url, data)
                        sse_session["session_id"] = (
                            data.split("session_id=")[-1] if "session_id=" in data else None
                        )
                    elif ev == "message" and data:
                        try:
                            msg = json.loads(data)
                        except Exception:
                            continue
                        mid = msg.get("id")
                        if mid is not None:
                            with pending_lock:
                                if mid in pending:
                                    pending[mid]["result"] = msg
                                    pending[mid]["event"].set()
                else:
                    buf = []
            else:
                buf.append(line)
    except Exception as e:
        if not stop_event.is_set():
            print(f"[reader] SSE 读取异常: {e}", file=sys.stderr)


def post_message(messages_url, api_key, payload):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        messages_url,
        data=data,
        headers={
            "X-API-Key": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
        method="POST",
    )
    try:
        resp = urllib.request.urlopen(req, timeout=TIMEOUT)
        return resp.status
    except urllib.error.HTTPError as e:
        return e.code


def rpc_call(messages_url, api_key, method, params=None, rid=None, wait=True):
    rid = rid if rid is not None else int(time.time() * 1000) % 100000
    payload = {"jsonrpc": "2.0", "id": rid, "method": method}
    if params is not None:
        payload["params"] = params
    with pending_lock:
        pending[rid] = {"event": threading.Event(), "result": None}
    post_message(messages_url, api_key, payload)
    if not wait:
        return None
    ok = pending[rid]["event"].wait(TIMEOUT)
    with pending_lock:
        res = pending.pop(rid, {}).get("result")
    if not ok:
        raise TimeoutError(f"调用 {method} 超时，未在 {TIMEOUT}s 内收到响应")
    return res


def run_mcp(sse_url, api_key, action="status", arguments=None, top_k=5):
    """通用调用：连 SSE、握手、调用一个工具，返回解析后的 result dict。
    action: status | list | search | raw(tool名)
    """
    sse_url = sse_url.rstrip("/") + "/"
    reader = threading.Thread(target=sse_reader, args=(sse_url, api_key), daemon=True)
    reader.start()
    deadline = time.time() + TIMEOUT
    while sse_session["messages_url"] is None and time.time() < deadline:
        time.sleep(0.1)
    if sse_session["messages_url"] is None:
        stop_event.set()
        raise RuntimeError("未收到 SSE endpoint 事件，连接失败")
    messages_url = sse_session["messages_url"]
    try:
        init = rpc_call(messages_url, api_key, "initialize", {
            "protocolVersion": PROTOCOL,
            "capabilities": {},
            "clientInfo": {"name": "qclaw-sse-client", "version": "1.0"},
        }, rid=1)
        rpc_call(messages_url, api_key, "notifications/initialized", wait=False, rid=2)
        if action == "list":
            return rpc_call(messages_url, api_key, "tools/list", rid=3)
        if action == "status":
            return rpc_call(messages_url, api_key, "tools/call",
                            {"name": "kb_status", "arguments": {}}, rid=3)
        if action == "search":
            return rpc_call(messages_url, api_key, "tools/call",
                            {"name": "kb_search", "arguments": arguments or {}}, rid=3)
        # raw tool name
        return rpc_call(messages_url, api_key, "tools/call",
                        {"name": action, "arguments": arguments or {}}, rid=3)
    finally:
        stop_event.set()


def search_text(sse_url, api_key, query, top_k=5):
    """返回 kb_search 的纯文本结果（便于脚本处理）。"""
    res = run_mcp(sse_url, api_key, "search", {"query": query, "top_k": top_k})
    return res["result"]["content"][0]["text"]


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)
    sse_url = sys.argv[1]
    api_key = sys.argv[2]
    tool_or_flag = sys.argv[3]
    try:
        if tool_or_flag == "--list":
            print(json.dumps(run_mcp(sse_url, api_key, "list"), ensure_ascii=False, indent=2))
        elif tool_or_flag == "--status":
            print(json.dumps(run_mcp(sse_url, api_key, "status"), ensure_ascii=False, indent=2))
        else:
            args = {}
            if len(sys.argv) >= 5:
                args = json.loads(sys.argv[4])
            print(json.dumps(run_mcp(sse_url, api_key, tool_or_flag, args), ensure_ascii=False, indent=2))
    except Exception as e:
        print(f"[error] {e}", file=sys.stderr)
        sys.exit(3)


if __name__ == "__main__":
    main()
