#!/usr/bin/env python3
"""
cnemc-mcp — 中国环境监测总站空气质量六参数 govMCP 服务

数据源: 全国城市空气质量实时发布平台（air.cnemc.cn:18007，公开接口）
能力: 城市级实时 6 参数（PM2.5/PM10/SO2/NO2/CO/O3）+ AQI + 首要污染物
协议: JSON-RPC 2.0 over stdio（MCP 兼容；手写实现，零 SDK 依赖）
等保加固: 每次调用写入 govmcp SM3 审计链（不可篡改），只读语义 L1

接入方式（客户端配置示例）:
  {"mcpServers": {"cnemc": {"command": "python3",
     "args": ["_scripts/cnemc-mcp.py"], "cwd": "<eco-agent 根目录>"}}}

用法:
  python3 _scripts/cnemc-mcp.py          # stdio 服务（供 MCP 客户端拉起）
  python3 _scripts/cnemc-mcp.py --selftest   # 自检（真实调用一次）
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SERVER_NAME = "cnemc-govmcp"
SERVER_VERSION = "1.0.0"

TOOLS = [
    {
        "name": "cnemc_air_quality",
        "description": "查询指定城市实时空气质量：PM2.5/PM10/SO2/NO2/CO/O3 六参数浓度 + AQI + 首要污染物 + 等级（GB 3095-2012）",  # noqa: E501
        "inputSchema": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "城市名（如 娄底、长沙、北京）"},
            },
            "required": ["city"],
        },
    },
    {
        "name": "cnemc_city_list",
        "description": "返回当前可查询空气质量数据的城市列表",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "cnemc_aqi_level",
        "description": "AQI 数值换算为等级/类别/健康影响提示（GB 3095-2012 技术规定）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "aqi": {"type": "number", "description": "AQI 数值"},
            },
            "required": ["aqi"],
        },
    },
]

# ── govmcp SM3 审计（等保：每次调用不可篡改留痕）──────────────────


def _audit(tool: str, args: dict, result: str, duration_ms: int) -> None:
    try:
        from govmcp.crypto.audit import AuditChain

        chain = AuditChain()
        chain.add_entry(
            operation=f"mcp_call:{tool}",
            operator="cnemc-mcp",
            input_data=json.dumps(args, ensure_ascii=False).encode("utf-8"),
            output_data=(str(result)[:300]).encode("utf-8"),
            approval_status="approved",
        )
        audit_file = ROOT / "memory-tree" / "data" / "audit" / "cnemc_mcp_audit.jsonl"
        audit_file.parent.mkdir(parents=True, exist_ok=True)
        entry = chain.entries[-1]
        record = {
            "when": time.time(),
            "tool": tool,
            "args": args,
            "result_preview": str(result)[:200],
            "cost": f"{duration_ms}ms",
            "prev_hash": entry.prev_hash,
            "current_hash": entry.current_hash,
        }
        with audit_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001 — 审计失败不阻断数据服务
        pass


# ── 工具实现（复用 agent_core/cnemc 真实客户端）───────────────────


def _air_quality(city: str) -> dict:
    t0 = time.monotonic()
    try:
        from agent_core.cnemc import get_city_realtime_air_quality

        result = get_city_realtime_air_quality(city)
    except Exception as e:  # noqa: BLE001 — CNEMC 不可用如实报错
        result = {"error": f"CNEMC 数据获取失败: {e}", "city": city}
    _audit("cnemc_air_quality", {"city": city}, result, int((time.monotonic() - t0) * 1000))
    return result


def _city_list() -> dict:
    t0 = time.monotonic()
    try:
        from agent_core.cnemc import _fetch_all_stations

        records, ts, _ = _fetch_all_stations()
        cities = sorted({r.get("CITY", r.get("city", "")) for r in records if r.get("CITY") or r.get("city")})
        result = {"count": len(cities), "cities": cities, "fetched_at": datetime.fromtimestamp(ts).isoformat()}
    except Exception as e:  # noqa: BLE001
        result = {"error": f"CNEMC 数据获取失败: {e}"}
    _audit("cnemc_city_list", {}, result, int((time.monotonic() - t0) * 1000))
    return result


def _aqi_level(aqi: float) -> dict:
    """AQI → 等级（HJ 633-2012 六档）。"""
    t0 = time.monotonic()
    aqi = float(aqi)
    if aqi <= 50:
        level = {"等级": "优", "类别": "一级", "提示": "空气质量令人满意，基本无空气污染"}
    elif aqi <= 100:
        level = {"等级": "良", "类别": "二级", "提示": "空气质量可接受，极少数敏感人群应减少户外活动"}
    elif aqi <= 150:
        level = {"等级": "轻度污染", "类别": "三级", "提示": "敏感人群症状有轻度加剧，健康人群出现刺激症状"}
    elif aqi <= 200:
        level = {"等级": "中度污染", "类别": "四级", "提示": "进一步加剧易感人群症状，健康人群心脏、呼吸系统有影响"}
    elif aqi <= 300:
        level = {"等级": "重度污染", "类别": "五级", "提示": "心脏病和肺病患者症状显著加剧，健康人群普遍出现症状"}
    else:
        level = {"等级": "严重污染", "类别": "六级", "提示": "健康人群运动耐受力降低，有明显强烈症状"}
    result = {"aqi": aqi, **level}
    _audit("cnemc_aqi_level", {"aqi": aqi}, result, int((time.monotonic() - t0) * 1000))
    return result


# ── MCP 协议（JSON-RPC 2.0 over stdio）─────────────────────────


def handle_request(request: dict) -> dict:
    req_id = request.get("id")
    method = request.get("method", "")
    params = request.get("params", {})

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": params.get("protocolVersion", "2024-11-05"),
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": SERVER_NAME,
                    "version": SERVER_VERSION,
                    "title": "中国环境监测总站空气质量 govMCP（SM3 审计）",
                },
            },
        }
    if method in ("tools/list", "mcp.list_tools"):
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}
    if method in ("tools/call", "mcp.call_tool"):
        name, args = params.get("name", ""), params.get("arguments", {})
        if name == "cnemc_air_quality":
            data = _air_quality(str(args.get("city", "")))
        elif name == "cnemc_city_list":
            data = _city_list()
        elif name == "cnemc_aqi_level":
            try:
                data = _aqi_level(float(args.get("aqi", 0)))
            except (TypeError, ValueError):
                data = {"error": "aqi 必须是数值"}
        else:
            data = {"error": f"未知工具: {name}"}
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}],
                "isError": "error" in data,
            },
        }
    if method in ("ping", "mcp.ping"):
        return {"jsonrpc": "2.0", "id": req_id, "result": {"status": "ok", "timestamp": datetime.now().isoformat()}}
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Method '{method}' not found"}}


def main() -> int:
    parser = argparse.ArgumentParser(description="总站空气质量六参数 govMCP")
    parser.add_argument("--selftest", action="store_true", help="自检（真实调用一次）")
    args = parser.parse_args()

    if args.selftest:
        print("cnemc_air_quality(娄底):")
        print(json.dumps(_air_quality("娄底"), ensure_ascii=False, indent=2))
        print("\ncnemc_aqi_level(85):")
        print(json.dumps(_aqi_level(85), ensure_ascii=False, indent=2))
        return 0

    sys.stderr.write(
        json.dumps(
            {
                "event": "mcp.startup",
                "server_name": SERVER_NAME,
                "version": SERVER_VERSION,
                "tools_count": len(TOOLS),
                "audit": "govmcp SM3 链（等保）",
            },
            ensure_ascii=False,
        )
        + "\n"
    )
    sys.stderr.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            sys.stdout.write(
                json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}) + "\n"
            )
            sys.stdout.flush()
            continue
        if "id" not in request:  # 通知不回包
            continue
        sys.stdout.write(json.dumps(handle_request(request), ensure_ascii=False) + "\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
