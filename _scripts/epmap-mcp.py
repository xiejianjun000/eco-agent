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


def _cred() -> tuple[str, str]:
    """返回 (secret_id, secret_key)——环境变量配置，不落仓库。"""
    return (
        os.environ.get("EPMAP_SECRET_ID", "").strip(),
        os.environ.get("EPMAP_SECRET_KEY", "").strip(),
    )


def _sign_headers() -> dict:
    """云市场 API 网关官方签名（青悦文档示例）：
    签名字符串 = "x-date: <UTC时间>"，HMAC-SHA1(SecretKey) → base64。
    Authorization = {"id", "x-date", "signature"} JSON。"""
    import base64
    import hashlib
    import hmac
    import uuid

    secret_id, secret_key = _cred()
    dt = datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S GMT')
    sign_str = f"x-date: {dt}"
    digest = hmac.new(secret_key.encode('utf-8'), sign_str.encode('utf-8'),
                      hashlib.sha1).digest()
    signature = base64.b64encode(digest).decode('utf-8')
    auth = json.dumps({"id": secret_id, "x-date": dt, "signature": signature})
    return {"request-id": str(uuid.uuid1()), "Authorization": auth}


def _fetch_epmap(endpoint: str, params: dict) -> dict:
    """调用青悦环境数据云（腾讯云市场 API 网关，官方签名）。"""
    import ssl
    import urllib.parse
    import urllib.request

    base_url = os.environ.get(
        "EPMAP_BASE_URL",
        "https://ap-shanghai.cloudmarket-apigw.com/service-q53mzqub/api/v2").rstrip("/")
    url = f"{base_url}/{endpoint}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    headers = _sign_headers()
    req = urllib.request.Request(url, headers=headers)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
        return json.loads(resp.read().decode('utf-8'))


def _token() -> str:
    return _cred()[0]


def _hmac_sha1(key: bytes, msg: str) -> str:
    import base64
    import hashlib
    import hmac

    return base64.b64encode(
        hmac.new(key, msg.encode("utf-8"), hashlib.sha1).digest()).decode()


def _no_token(tool: str, args: dict, t0: float) -> dict:
    result = {"error": "EPMAP 接入参数不全——需要 EPMAP_SECRET_ID / EPMAP_SECRET_KEY / "
                       "EPMAP_SOURCE（签名水印）/ EPMAP_BASE_URL（网关端点），"
                       "见青悦申请 API 时提供的接入文档", "status": "skeleton"}
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
        sid, sk = _cred()
        print("EPMAP_SECRET_ID:", "已配置" if sid else "缺失")
        print("EPMAP_SECRET_KEY:", "已配置" if sk else "缺失")
        try:
            result = _fetch_epmap("surface_water/stations", {})
            print("接口调用: HTTP 200（签名通过）")
            print(json.dumps(result, ensure_ascii=False, indent=1)[:400])
        except Exception as e:  # noqa: BLE001
            print("接口调用失败:", e)
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
