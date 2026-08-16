#!/usr/bin/env python3
"""
tests/modules/test_weather_mcp.py — 气象 govMCP 协议测试

覆盖: stdio JSON-RPC 协议（initialize/tools/list/ping/call）、
      真实数据、城市码解析、SM3 审计落盘。
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

SERVER = ROOT / "_scripts" / "weather-mcp.py"


def _rpc(request: dict, timeout: int = 120) -> dict:
    r = subprocess.run([sys.executable, str(SERVER)],
                       input=json.dumps(request) + "\n",
                       capture_output=True, text=True, timeout=timeout)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_initialize():
    resp = _rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                 "params": {"protocolVersion": "2024-11-05"}})
    assert resp["result"]["serverInfo"]["name"] == "weather-govmcp"


def test_tools_list():
    resp = _rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = [t["name"] for t in resp["result"]["tools"]]
    assert names == ["weather_now", "weather_forecast", "weather_city_list"]


def test_city_list():
    resp = _rpc({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                 "params": {"name": "weather_city_list", "arguments": {}}})
    content = json.loads(resp["result"]["content"][0]["text"])
    assert content["cities"]["冷水江"] == "101250803"


def test_weather_now_real():
    resp = _rpc({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                 "params": {"name": "weather_now", "arguments": {"city": "冷水江"}}},
                timeout=120)
    content = json.loads(resp["result"]["content"][0]["text"])
    if "error" in content:
        assert "失败" in content["error"]  # 网络不可达时如实报错
    else:
        assert content["city"] == "冷水江"
        for key in ("temp_c", "humidity", "wind_dir", "weather", "aqi"):
            assert key in content


def test_weather_now_by_code():
    """直接用 101 城市码查询。"""
    resp = _rpc({"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                 "params": {"name": "weather_now", "arguments": {"city": "101250803"}}},
                timeout=120)
    content = json.loads(resp["result"]["content"][0]["text"])
    if "error" not in content:
        assert content["code"] == "101250803"


def test_unknown_city():
    resp = _rpc({"jsonrpc": "2.0", "id": 6, "method": "tools/call",
                 "params": {"name": "weather_now", "arguments": {"city": "不存在市"}}})
    content = json.loads(resp["result"]["content"][0]["text"])
    assert "未知城市" in content["error"]


def test_audit_written():
    audit_file = ROOT / "memory-tree" / "data" / "audit" / "weather_mcp_audit.jsonl"
    assert audit_file.exists(), "审计链未落盘"
    lines = audit_file.read_text(encoding="utf-8").strip().splitlines()
    assert lines
    record = json.loads(lines[-1])
    assert record["current_hash"] and record["prev_hash"]
