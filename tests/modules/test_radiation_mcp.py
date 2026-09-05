#!/usr/bin/env python3
"""
tests/modules/test_radiation_mcp.py — 全国辐射监测 govMCP 协议测试

覆盖: stdio JSON-RPC 协议（initialize/tools/list/ping/call）、
      真实官方数据（31 省 + 湖南站点）、SM3 审计落盘。
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

SERVER = ROOT / "_scripts" / "radiation-mcp.py"


def _rpc(request: dict, timeout: int = 120) -> dict:
    r = subprocess.run(
        [sys.executable, str(SERVER)], input=json.dumps(request) + "\n", capture_output=True, text=True, timeout=timeout
    )
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_initialize():
    resp = _rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05"}})
    assert resp["result"]["serverInfo"]["name"] == "radiation-govmcp"


def test_tools_list():
    resp = _rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = [t["name"] for t in resp["result"]["tools"]]
    assert names == ["radiation_provinces", "radiation_stations", "radiation_baseline"]


def test_provinces_real():
    """官方直连：31 省剂量率汇总（网络不可达时如实报错）。"""
    resp = _rpc(
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "radiation_provinces", "arguments": {}}},
        timeout=120,
    )
    content = json.loads(resp["result"]["content"][0]["text"])
    if "error" in content:
        assert "失败" in content["error"]
    else:
        assert content["count"] == 31
        assert content["unit"] == "nGy/h"
        bj = [p for p in content["provinces"] if p["province"] == "北京"][0]
        assert 39 <= bj["dose_rate_nGyh"] <= 500  # 本底合理区间


def test_stations_hunan():
    resp = _rpc(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "radiation_stations", "arguments": {"province": "湖南"}},
        },
        timeout=120,
    )
    content = json.loads(resp["result"]["content"][0]["text"])
    if "error" not in content:
        assert content["count"] >= 1
        assert all("dose_rate_nGyh" in s for s in content["stations"])


def test_unknown_province():
    resp = _rpc(
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": "radiation_stations", "arguments": {"province": "不存在省"}},
        }
    )
    content = json.loads(resp["result"]["content"][0]["text"])
    assert "未知省份" in content["error"]


def test_baseline():
    resp = _rpc({"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "radiation_baseline", "arguments": {}}})
    content = json.loads(resp["result"]["content"][0]["text"])
    assert "39.3-403.5" in content["baseline_range"]


def test_audit_written():
    audit_file = ROOT / "memory-tree" / "data" / "audit" / "radiation_mcp_audit.jsonl"
    assert audit_file.exists()
    lines = audit_file.read_text(encoding="utf-8").strip().splitlines()
    assert lines
    record = json.loads(lines[-1])
    assert record["current_hash"] and record["prev_hash"]
