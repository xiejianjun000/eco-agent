#!/usr/bin/env python3
"""
radiation-mcp — 全国辐射环境监测 govMCP 服务（官方直连，免 key）

数据源: 生态环境部辐射环境监测技术中心（rmtc.org.cn）
        全国空气吸收剂量率发布系统（data.rmtc.org.cn/gis/）
        依据《关于实时发布国家辐射环境监测网自动监测数据的通知》（环保部 2015）
能力: 31 省空气吸收剂量率实时数据（nGy/h）——环境质量监测点/核电厂监测点
协议: JSON-RPC 2.0 over stdio（MCP 兼容；手写实现，零 SDK 依赖）
等保: govmcp SM3 审计链（每次调用）；数据服务端渲染，正则解析，缓存 1h

接入方式:
  {"mcpServers": {"radiation": {"command": "python3",
     "args": ["_scripts/radiation-mcp.py"], "cwd": "<eco-agent 根目录>"}}}
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SERVER_NAME = "radiation-govmcp"
SERVER_VERSION = "1.0.0"
BASE = "https://data.rmtc.org.cn/gis"

# 本底参考区间（页面官方口径）
BASELINE_RANGE = "39.3-403.5 nGy/h（全国本底水平前期调查范围）"

TOOLS = [
    {
        "name": "radiation_provinces",
        "description": "全国 31 省空气吸收剂量率实时汇总（省代表站数值 + 更新时间，单位 nGy/h）",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "radiation_stations",
        "description": "指定省份全部辐射监测站点明细（环境质量监测点或核电厂监测点）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "province": {"type": "string", "description": "省份名（如 湖南）或省代码（如 43）"},
            },
            "required": ["province"],
        },
    },
    {
        "name": "radiation_baseline",
        "description": "返回全国本底水平参考区间与数据解读说明",
        "inputSchema": {"type": "object", "properties": {}},
    },
]

# ── 数据抓取（服务端渲染解析 + 1h 缓存）────────────────────


def _audit(tool: str, args: dict, result: str, duration_ms: int) -> None:
    try:
        from govmcp.crypto.audit import AuditChain

        chain = AuditChain()
        chain.add_entry(
            operation=f"mcp_call:{tool}",
            operator="radiation-mcp",
            input_data=json.dumps(args, ensure_ascii=False).encode("utf-8"),
            output_data=(str(result)[:300]).encode("utf-8"),
            approval_status="approved",
        )
        audit_file = ROOT / "memory-tree" / "data" / "audit" / "radiation_mcp_audit.jsonl"
        audit_file.parent.mkdir(parents=True, exist_ok=True)
        entry = chain.entries[-1]
        with audit_file.open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "when": time.time(),
                        "tool": tool,
                        "args": args,
                        "result_preview": str(result)[:200],
                        "cost": f"{duration_ms}ms",
                        "prev_hash": entry.prev_hash,
                        "current_hash": entry.current_hash,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    except Exception:  # noqa: BLE001
        pass


def _http_get(path: str) -> str:
    import urllib.request

    req = urllib.request.Request(f"{BASE}/{path}", headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=25) as resp:
        return resp.read().decode("utf-8", errors="replace")


_province_cache: dict = {}
_station_cache: dict = {}
_cache_lock = threading.Lock()


def _provinces_raw() -> list[dict]:
    with _cache_lock:
        if _province_cache.get("ts", 0) > time.time() - 3600:
            return _province_cache["data"]
    html = _http_get("listtype0M.html")
    body = re.search(r"<body[^>]*>(.*)</body>", html, re.S)
    body = body.group(1) if body else html
    out = []
    for item in re.findall(r"<li class=\"datali\">(.*?)</li>", body, re.S):
        link = re.search(r'href="listsation0_(\d+)M\.html">\s*(.*?)\s*</a>', item, re.S)
        val = re.search(r'class="label">\s*([\d.]+)\s*nGy/h', item)
        t = re.search(r'class="showtime">\s*([\d-]+)', item)
        if link and val:
            out.append(
                {
                    "province": link.group(2).strip().split("(")[0].strip(),
                    "station": (link.group(2).strip().split("(")[1].rstrip(")").strip() if "(" in link.group(2) else ""),
                    "code": link.group(1),
                    "dose_rate_nGyh": float(val.group(1)),
                    "date": t.group(1) if t else "",
                }
            )
    with _cache_lock:
        _province_cache["ts"] = time.time()
        _province_cache["data"] = out
    return out


def _stations_raw(code: str) -> list[dict]:
    key = code
    with _cache_lock:
        if _station_cache.get(key, {}).get("ts", 0) > time.time() - 3600:
            return _station_cache[key]["data"]
    html = _http_get(f"listsation0_{code}M.html")
    body = re.search(r"<body[^>]*>(.*)</body>", html, re.S)
    body = body.group(1) if body else html
    out = []
    for item in re.findall(r"<li class=\"datali\">(.*?)</li>", body, re.S):
        name = re.search(r'<div class="divname">\s*(.*?)\s*</div>', item, re.S)
        val = re.search(r'class="label">\s*([\d.]+)\s*nGy/h', item)
        t = re.search(r'class="showtime">\s*([\d-]+)', item)
        if name and val:
            out.append(
                {"station": name.group(1).strip(), "dose_rate_nGyh": float(val.group(1)), "date": t.group(1) if t else ""}
            )
    with _cache_lock:
        _station_cache[key] = {"ts": time.time(), "data": out}
    return out


# ── 工具实现 ───────────────────────────────────────────────


def _province_code(province: str) -> str:
    if re.fullmatch(r"\d{2}", province):
        return province
    for p in _provinces_raw():
        if p["province"] == province.strip():
            return p["code"]
    return ""


def _radiation_provinces() -> dict:
    t0 = time.monotonic()
    try:
        provinces = _provinces_raw()
        result = {"count": len(provinces), "unit": "nGy/h", "baseline_range": BASELINE_RANGE, "provinces": provinces}
    except Exception as e:  # noqa: BLE001
        result = {"error": f"辐射数据获取失败: {e}"}
    _audit("radiation_provinces", {}, result, int((time.monotonic() - t0) * 1000))
    return result


def _radiation_stations(province: str) -> dict:
    t0 = time.monotonic()
    code = _province_code(province)
    if not code:
        result = {"error": f"未知省份: {province}（用 radiation_provinces 查省份名/代码）"}
    else:
        try:
            stations = _stations_raw(code)
            result = {"province": province, "code": code, "unit": "nGy/h", "count": len(stations), "stations": stations}
        except Exception as e:  # noqa: BLE001
            result = {"error": f"站点数据获取失败: {e}"}
    _audit("radiation_stations", {"province": province}, result, int((time.monotonic() - t0) * 1000))
    return result


def _radiation_baseline() -> dict:
    result = {
        "baseline_range": BASELINE_RANGE,
        "note": "全国空气吸收剂量率单位为 nGy/h；本底范围 39.3-403.5 nGy/h，"
        "各站读数在本底范围内属正常。数据来源：生态环境部辐射环境监测技术中心"
        "（data.rmtc.org.cn，依据环保部 2015 年实时发布通知）。",
    }
    _audit("radiation_baseline", {}, result, 0)
    return result


# ── MCP 协议 ───────────────────────────────────────────────


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
                    "title": "全国辐射环境监测 govMCP（官方直连，SM3 审计）",
                },
            },
        }
    if method in ("tools/list", "mcp.list_tools"):
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}
    if method in ("tools/call", "mcp.call_tool"):
        name, args = params.get("name", ""), params.get("arguments", {})
        if name == "radiation_provinces":
            data = _radiation_provinces()
        elif name == "radiation_stations":
            data = _radiation_stations(str(args.get("province", "")))
        elif name == "radiation_baseline":
            data = _radiation_baseline()
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
    parser = argparse.ArgumentParser(description="全国辐射监测 govMCP")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()

    if args.selftest:
        print(json.dumps(_radiation_provinces(), ensure_ascii=False, indent=1)[:800])
        print("\n湖南站点:")
        print(json.dumps(_radiation_stations("湖南"), ensure_ascii=False, indent=1)[:500])
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
        if "id" not in request:
            continue
        sys.stdout.write(json.dumps(handle_request(request), ensure_ascii=False) + "\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
