#!/usr/bin/env python3
"""
epmap-mcp — 环境数据云（epmap.org / 上海青悦环保）govMCP 骨架

数据源: 环境数据云（国控/省控空气质量、国家地表水水质、环境辐射、水文、碳排放）
认证: EPMAP_TOKEN 环境变量（需向 epmap.org 申请授权）
状态: 骨架就绪——工具协议/审计/城市表齐备；数据接口待 token 就位后
      按 epmap 后台接口文档填 _fetch_epmap 一处即可全部启用。

接入方式:
  export EPMAP_TOKEN=<申请到的 token>
  {"mcpServers": {"epmap": {"command": "python3",
     "args": ["_scripts/epmap-mcp.py"], "cwd": "<eco-agent 根目录>"}}}
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SERVER_NAME = "epmap-govmcp"
SERVER_VERSION = "0.1.0-skeleton"

TOOLS = [
    {
        "name": "water_quality",
        "description": "国家地表水水质断面数据（国控/省控断面，pH/DO/COD/氨氮/总磷等）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "basin": {"type": "string", "description": "流域/水系（如 资江、长江流域）"},
                "site": {"type": "string", "description": "断面名称（可选）"},
                "date": {"type": "string", "description": "数据日期 YYYY-MM-DD（可选，默认最新）"},
            },
            "required": [],
        },
    },
    {
        "name": "air_quality_national",
        "description": "国控空气质量站点数据（六参数小时/日均值，CNEMC 之外的独立备源）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "城市名（如 冷水江）"},
                "date": {"type": "string", "description": "数据日期（可选）"},
            },
            "required": [],
        },
    },
    {
        "name": "radiation_monitoring",
        "description": "环境辐射监测数据（γ辐射剂量率等）",
        "inputSchema": {"type": "object", "properties": {}},
    },
]

CITY_HINTS = {
    "冷水江": {"basin": "资水", "province": "湖南"},
    "娄底": {"basin": "资水", "province": "湖南"},
    "长沙": {"basin": "湘江", "province": "湖南"},
}


def _audit(tool: str, args: dict, result: str, duration_ms: int) -> None:
    try:
        from govmcp.crypto.audit import AuditChain

        chain = AuditChain()
        chain.add_entry(operation=f"mcp_call:{tool}", operator="epmap-mcp",
                        input_data=json.dumps(args, ensure_ascii=False).encode("utf-8"),
                        output_data=(str(result)[:300]).encode("utf-8"),
                        approval_status="approved")
        audit_file = ROOT / "memory-tree" / "data" / "audit" / "epmap_mcp_audit.jsonl"
        audit_file.parent.mkdir(parents=True, exist_ok=True)
        entry = chain.entries[-1]
        with audit_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"when": time.time(), "tool": tool, "args": args,
                                "result_preview": str(result)[:200],
                                "cost": f"{duration_ms}ms", "prev_hash": entry.prev_hash,
                                "current_hash": entry.current_hash}, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001
        pass


def _token() -> str:
    return os.environ.get("EPMAP_TOKEN", "").strip()


def _fetch_epmap(endpoint: str, params: dict) -> dict:
    """TODO: token 就位后按 epmap 后台接口文档实现——
    通常形如 GET/POST https://api.epmap.org/<endpoint>?token=<EPMAP_TOKEN>&...
    返回解析后的 JSON。此处为骨架占位。"""
    raise NotImplementedError(
        "EPMAP_TOKEN 未配置或接口未实现——请先向 epmap.org 申请授权 token，"
        "并设置环境变量 EPMAP_TOKEN；接口实现见 _fetch_epmap 的 TODO")


def _no_token(tool: str, args: dict, t0: float) -> dict:
    result = {"error": "未配置 EPMAP_TOKEN（需向 epmap.org 申请环境数据云授权后，"
                       "export EPMAP_TOKEN=<token>）", "status": "skeleton"}
    _audit(tool, args, result, int((time.monotonic() - t0) * 1000))
    return result


def _call(tool: str, args: dict) -> dict:
    t0 = time.monotonic()
    if not _token():
        return _no_token(tool, args, t0)
    try:
        if tool == "water_quality":
            result = _fetch_epmap("water/quality", args)
        elif tool == "air_quality_national":
            result = _fetch_epmap("air/national", args)
        else:
            result = _fetch_epmap("radiation", args)
    except NotImplementedError as e:
        result = {"error": str(e), "status": "skeleton"}
    except Exception as e:  # noqa: BLE001
        result = {"error": f"epmap 数据获取失败: {e}"}
    _audit(tool, args, result, int((time.monotonic() - t0) * 1000))
    return result


def handle_request(request: dict) -> dict:
    req_id = request.get("id")
    method = request.get("method", "")
    params = request.get("params", {})

    if method == "initialize":
        return {"jsonrpc": "2.0", "id": req_id, "result": {
            "protocolVersion": params.get("protocolVersion", "2024-11-05"),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION,
                           "title": "环境数据云 govMCP（骨架：待 EPMAP_TOKEN）"},
        }}
    if method in ("tools/list", "mcp.list_tools"):
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}
    if method in ("tools/call", "mcp.call_tool"):
        name, args = params.get("name", ""), params.get("arguments", {})
        data = _call(name, args) if name in {t["name"] for t in TOOLS} else \
            {"error": f"未知工具: {name}"}
        return {"jsonrpc": "2.0", "id": req_id, "result": {
            "content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}],
            "isError": "error" in data,
        }}
    if method in ("ping", "mcp.ping"):
        return {"jsonrpc": "2.0", "id": req_id,
                "result": {"status": "ok", "timestamp": datetime.now().isoformat()}}
    return {"jsonrpc": "2.0", "id": req_id,
            "error": {"code": -32601, "message": f"Method '{method}' not found"}}


def main() -> int:
    parser = argparse.ArgumentParser(description="环境数据云 govMCP（骨架）")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()

    if args.selftest:
        print("token:", "已配置" if _token() else "未配置（骨架模式）")
        print(json.dumps(_call("water_quality", {"basin": "资水"}), ensure_ascii=False, indent=2))
        return 0

    sys.stderr.write(json.dumps({
        "event": "mcp.startup", "server_name": SERVER_NAME,
        "version": SERVER_VERSION, "tools_count": len(TOOLS),
        "token": "configured" if _token() else "missing"}, ensure_ascii=False) + "\n")
    sys.stderr.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": None,
                                         "error": {"code": -32700, "message": "Parse error"}}) + "\n")
            sys.stdout.flush()
            continue
        if "id" not in request:
            continue
        sys.stdout.write(json.dumps(handle_request(request), ensure_ascii=False) + "\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
