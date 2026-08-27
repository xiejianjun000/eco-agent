#!/usr/bin/env python3
"""
tests/modules/test_trace_audit.py — 执行轨迹审计（govmcp SM3 等保台账）测试

覆盖: 五要素记录、跨记录链衔接、verify 正常链、
      三种篡改检测（业务字段/哈希字段/删行）。
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from agent_core.trace_audit import TraceAudit  # noqa: E402


@pytest.fixture()
def audit(tmp_path):
    return TraceAudit(base_dir=tmp_path)


def _seed(audit):
    audit.record_tool_call("statute_lookup", {"article": "1054"}, "第一千零五十四条原文", 120, "L1", "allow")
    audit.record_llm_call("deepseek-v4-pro", 1, 2100, input_chars=30)
    audit.record_trace("查法典", "回复内容", 2, 3000, "deepseek-v4-pro")


def test_verify_clean_chain(audit):
    _seed(audit)
    v = audit.verify()
    assert v["ok"] is True
    assert v["entries"] == 3
    assert v["last_hash"]


def test_five_elements_present(audit):
    """等保五要素: when/who/what/result/cost 每条必在。"""
    audit.record_tool_call("t", {}, "r", 10, "L1", "allow")
    record = json.loads(audit.chain_path.read_text().splitlines()[0])
    for elem in ("when", "who", "what", "result", "cost"):
        assert elem in record, f"缺五要素: {elem}"


def test_tamper_business_field_detected(audit):
    _seed(audit)
    lines = audit.chain_path.read_text().splitlines()
    e = json.loads(lines[1])
    e["result"] = "被篡改"
    lines[1] = json.dumps(e, ensure_ascii=False)
    audit.chain_path.write_text("\n".join(lines) + "\n")
    v = audit.verify()
    assert v["ok"] is False
    assert "篡改" in v["error"]


def test_tamper_hash_detected(audit):
    _seed(audit)
    lines = audit.chain_path.read_text().splitlines()
    e = json.loads(lines[0])
    e["current_hash"] = "deadbeef"
    lines[0] = json.dumps(e, ensure_ascii=False)
    audit.chain_path.write_text("\n".join(lines) + "\n")
    assert audit.verify()["ok"] is False


def test_delete_row_detected(audit):
    _seed(audit)
    lines = audit.chain_path.read_text().splitlines()
    audit.chain_path.write_text("\n".join(lines[1:]) + "\n")
    assert audit.verify()["ok"] is False


def test_cross_record_chaining(audit):
    """跨记录（跨重启模拟）链衔接正确。"""
    _seed(audit)
    # 新实例（模拟重启）继续追加
    audit2 = TraceAudit(base_dir=audit.base_dir)
    audit2.record_tool_call("statute_search", {"keyword": "逃避监管"}, "结果", 50, "L1", "allow")
    v = audit2.verify()
    assert v["ok"] is True
    assert v["entries"] == 4
