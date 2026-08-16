#!/usr/bin/env python3
"""
tests/modules/test_cnemc_mcp.py — 总站空气质量 govMCP 协议测试

覆盖: stdio JSON-RPC 协议（initialize/tools/list/tools/call/ping）、
      真实数据、SM3 审计落盘。
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

SERVER = ROOT / "_scripts" / "cnemc-mcp.py"


def _rpc(request: dict, timeout: int = 120) -> dict:
    """经 stdio 协议调用一次，返回响应 dict。"""
    r = subprocess.run([sys.executable, str(SERVER)],
                       input=json.dumps(request) + "\n",
                       capture_output=True, text=True, timeout=timeout)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_initialize():
    resp = _rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                 "params": {"protocolVersion": "2024-11-05"}})
    assert resp["result"]["serverInfo"]["name"] == "cnemc-govmcp"
    assert resp["result"]["capabilities"]["tools"] == {}


def test_tools_list():
    resp = _rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = [t["name"] for t in resp["result"]["tools"]]
    assert names == ["cnemc_air_quality", "cnemc_city_list", "cnemc_aqi_level"]


def test_ping():
    resp = _rpc({"jsonrpc": "2.0", "id": 3, "method": "ping"})
    assert resp["result"]["status"] == "ok"


def test_air_quality_real():
    """真实调用总站（网络可达时；失败走 CNEMC 错误响应不算协议错误）。"""
    # 真实网络调用：CNEMC 接口慢（10s 超时+2 重试+全站抓取），给足时间
    resp = _rpc({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                 "params": {"name": "cnemc_air_quality", "arguments": {"city": "娄底"}}},
                timeout=300)
    content = json.loads(resp["result"]["content"][0]["text"])
    if "error" in content:
        # 网络不可达时如实报错（协议仍正确）
        assert "CNEMC" in content["error"]
    else:
        for key in ("aqi", "pm25", "pm10", "so2", "no2", "co", "o3"):
            assert key in content, f"缺六参数字段: {key}"


def test_aqi_level_local():
    """AQI 换算为本地计算（离线可测）。"""
    resp = _rpc({"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                 "params": {"name": "cnemc_aqi_level", "arguments": {"aqi": 85}}})
    content = json.loads(resp["result"]["content"][0]["text"])
    assert content["等级"] == "良"
    assert content["类别"] == "二级"


def test_unknown_tool():
    resp = _rpc({"jsonrpc": "2.0", "id": 6, "method": "tools/call",
                 "params": {"name": "no_such_tool", "arguments": {}}})
    content = json.loads(resp["result"]["content"][0]["text"])
    assert "未知工具" in content["error"]
    assert resp["result"]["isError"] is True


def test_audit_written():
    """SM3 审计落盘（等保留痕）。"""
    _rpc({"jsonrpc": "2.0", "id": 7, "method": "tools/call",
          "params": {"name": "cnemc_aqi_level", "arguments": {"aqi": 50}}})
    audit_file = ROOT / "memory-tree" / "data" / "audit" / "cnemc_mcp_audit.jsonl"
    assert audit_file.exists()
    lines = audit_file.read_text(encoding="utf-8").strip().splitlines()
    assert lines, "审计链为空"
    record = json.loads(lines[-1])
    assert record["current_hash"] and record["prev_hash"], "SM3 哈希缺失"
