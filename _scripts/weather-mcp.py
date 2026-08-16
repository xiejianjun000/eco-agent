#!/usr/bin/env python3
"""
weather-mcp — 气象 govMCP 服务（中国天气网公开数据，气象局旗下）

数据源: weather.com.cn 公开接口（d1.weather.com.cn，101 城市码体系）
能力: 城市实时天气（温度/湿度/风/能见度/AQI）+ 今日明日预报
协议: JSON-RPC 2.0 over stdio（MCP 兼容；手写实现，零 SDK 依赖）
等保加固: 每次调用写入 govmcp SM3 审计链（不可篡改），只读语义 L1

接入方式（客户端配置示例）:
  {"mcpServers": {"weather": {"command": "python3",
     "args": ["_scripts/weather-mcp.py"], "cwd": "<eco-agent 根目录>"}}}

用法:
  python3 _scripts/weather-mcp.py               # stdio 服务
  python3 _scripts/weather-mcp.py --selftest    # 自检（真实调用）
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SERVER_NAME = "weather-govmcp"
SERVER_VERSION = "1.0.0"

# 城市 → 101 代码表（湖南执法辖区优先，可扩展）
CITY_CODES = {
    "长沙": "101250101", "娄底": "101250801", "双峰": "101250802",
    "冷水江": "101250803", "涟源": "101250804", "新化": "101250805",
    "北京": "101010100", "广州": "101280101",
}

_BASE = "http://d1.weather.com.cn"
_HEADERS = {
    "Referer": "http://www.weather.com.cn/",
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
}

TOOLS = [
    {
        "name": "weather_now",
        "description": "查询城市实时天气：温度/湿度/风向风速/能见度/气压/降雨/AQI/天气现象/更新时间",
        "inputSchema": {
            "type": "object",
            "properties": {"city": {"type": "string", "description": "城市名（如 冷水江、娄底、长沙）或 101 城市码"}},
            "required": ["city"],
        },
    },
    {
        "name": "weather_forecast",
        "description": "查询城市今日与明日天气预报（天气现象/气温/风向）",
        "inputSchema": {
            "type": "object",
            "properties": {"city": {"type": "string", "description": "城市名或 101 城市码"}},
            "required": ["city"],
        },
    },
    {
        "name": "weather_city_list",
        "description": "返回已内置的城市与 101 城市码对照表",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def _audit(tool: str, args: dict, result: str, duration_ms: int) -> None:
    try:
        from govmcp.crypto.audit import AuditChain

        chain = AuditChain()
        chain.add_entry(operation=f"mcp_call:{tool}", operator="weather-mcp",
                        input_data=json.dumps(args, ensure_ascii=False).encode("utf-8"),
                        output_data=(str(result)[:300]).encode("utf-8"),
                        approval_status="approved")
        audit_file = ROOT / "memory-tree" / "data" / "audit" / "weather_mcp_audit.jsonl"
        audit_file.parent.mkdir(parents=True, exist_ok=True)
        entry = chain.entries[-1]
        with audit_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"when": time.time(), "tool": tool, "args": args,
                                "result_preview": str(result)[:200],
                                "cost": f"{duration_ms}ms", "prev_hash": entry.prev_hash,
                                "current_hash": entry.current_hash}, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001 — 审计失败不阻断数据服务
        pass


def _resolve_code(city: str) -> str:
    if re.fullmatch(r"101\d{6}", city):
        return city
    return CITY_CODES.get(city.strip(), "")


def _fetch(path: str) -> str:
    import urllib.request

    req = urllib.request.Request(f"{_BASE}{path}", headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=12) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _weather_now(city: str) -> dict:
    t0 = time.monotonic()
    code = _resolve_code(city)
    if not code:
        result = {"error": f"未知城市: {city}（可用 weather_city_list 查内置城市，或直接用 101 城市码）"}
    else:
        try:
            raw = _fetch(f"/sk_2d/{code}.html")
            m = re.search(r"dataSK=(\{.*?\})", raw)
            data = json.loads(m.group(1)) if m else {}
            if not data:
                result = {"error": "天气数据解析失败"}
            else:
                result = {
                    "city": data.get("cityname", city), "code": data.get("city", code),
                    "temp_c": data.get("temp"), "humidity": data.get("SD"),
                    "wind_dir": data.get("WD"), "wind_level": data.get("WS"),
                    "visibility_km": data.get("njd"), "pressure_hpa": data.get("qy"),
                    "rain_mm": data.get("rain"), "rain24h_mm": data.get("rain24h"),
                    "aqi": data.get("aqi"), "aqi_pm25": data.get("aqi_pm25"),
                    "weather": data.get("weather"),
                    "updated": data.get("date", "") + " " + data.get("time", ""),
                }
        except Exception as e:  # noqa: BLE001
            result = {"error": f"气象数据获取失败: {e}", "city": city}
    _audit("weather_now", {"city": city}, result, int((time.monotonic() - t0) * 1000))
    return result


def _weather_forecast(city: str) -> dict:
    t0 = time.monotonic()
    code = _resolve_code(city)
    if not code:
        result = {"error": f"未知城市: {city}"}
    else:
        try:
            raw = _fetch(f"/weather_index/{code}.html")
            m = re.search(r"cityDZ =(\{.*?\});", raw)
            data = json.loads(m.group(1)) if m else {}
            info = data.get("weatherinfo", {})
            result = {
                "city": info.get("city", city), "code": code,
                "today": {"weather": info.get("weather"), "temp_high": info.get("temp"),
                          "temp_low": info.get("tempn"), "wind": info.get("wd") + " " + info.get("ws", "")},
                "forecast_time": info.get("fctime", ""),
            }
        except Exception as e:  # noqa: BLE001
            result = {"error": f"预报获取失败: {e}", "city": city}
    _audit("weather_forecast", {"city": city}, result, int((time.monotonic() - t0) * 1000))
    return result


def _city_list() -> dict:
    result = {"count": len(CITY_CODES), "cities": CITY_CODES}
    _audit("weather_city_list", {}, result, 0)
    return result


# ── MCP 协议 ───────────────────────────────────────────────


def handle_request(request: dict) -> dict:
    req_id = request.get("id")
    method = request.get("method", "")
    params = request.get("params", {})

    if method == "initialize":
        return {"jsonrpc": "2.0", "id": req_id, "result": {
            "protocolVersion": params.get("protocolVersion", "2024-11-05"),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION,
                           "title": "气象 govMCP（中国天气网公开数据，SM3 审计）"},
        }}
    if method in ("tools/list", "mcp.list_tools"):
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}
    if method in ("tools/call", "mcp.call_tool"):
        name, args = params.get("name", ""), params.get("arguments", {})
        if name == "weather_now":
            data = _weather_now(str(args.get("city", "")))
        elif name == "weather_forecast":
            data = _weather_forecast(str(args.get("city", "")))
        elif name == "weather_city_list":
            data = _city_list()
        else:
            data = {"error": f"未知工具: {name}"}
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
    parser = argparse.ArgumentParser(description="气象 govMCP")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()

    if args.selftest:
        for c in ("冷水江", "娄底"):
            print(f"weather_now({c}):")
            print(json.dumps(_weather_now(c), ensure_ascii=False, indent=2))
            print(f"\nweather_forecast({c}):")
            print(json.dumps(_weather_forecast(c), ensure_ascii=False, indent=2))
        return 0

    sys.stderr.write(json.dumps({
        "event": "mcp.startup", "server_name": SERVER_NAME,
        "version": SERVER_VERSION, "tools_count": len(TOOLS),
        "audit": "govmcp SM3 链（等保）"}, ensure_ascii=False) + "\n")
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
