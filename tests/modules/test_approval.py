"""L4 审批栈测试：request→pending / decide allow·deny / 审计对落链 /
answerer 链 fail-closed / policy=never 不产生 pending / jsonl 持久化重载"""
import pytest

from agent_core.approval import ApprovalService
from agent_core.prompt_engine import PromptAuditChain, PromptEngine


@pytest.fixture()
def svc(tmp_path):
    return ApprovalService(policy="ask", answerers=["admin"],
                           path=tmp_path / "approvals.jsonl")


def test_request_pending(svc):
    r = svc.request("submit_report", {"company": "X"})
    assert r["id"] and r["status"] == "pending"
    pending = svc.list_pending()
    assert len(pending) == 1
    assert pending[0]["id"] == r["id"]
    assert pending[0]["scope"] == "submit_report"
    assert pending[0]["detail"] == {"company": "X"}


def test_decide_allow_and_deny(svc):
    rid_allow = svc.request("submit_report", {})["id"]
    r = svc.decide(rid_allow, True, "admin", "人工批准")
    assert r["status"] == "allowed" and r["allow"] is True

    rid_deny = svc.request("submit_report", {})["id"]
    r2 = svc.decide(rid_deny, False, "admin", "人工拒绝")
    assert r2["status"] == "denied" and r2["allow"] is False

    # 决定后的请求退出 pending 队列
    assert svc.list_pending() == []


def test_audit_pair_written(tmp_path, monkeypatch):
    eng = PromptEngine(audit_chain=PromptAuditChain(tmp_path / "audit.jsonl"))
    monkeypatch.setattr("agent_core.prompt_engine._engine", eng)
    svc = ApprovalService(policy="ask", answerers=["admin"],
                          path=tmp_path / "approvals.jsonl")
    rid = svc.request("submit_report", {"company": "X"})["id"]
    svc.decide(rid, True, "admin", "批准")

    entries = [e for e in eng.audit.tail(20) if e["source"] == "approval"]
    assert len(entries) >= 2
    assert any("asked" in e["content"] for e in entries)          # asked 元数据
    decided = [e for e in entries if "decided" in e["content"]]   # decided 决定
    assert decided and decided[-1]["accepted"] is True
    # 审计对同源（task_id 均为请求 id）
    assert all(e["task_id"] == rid for e in entries)


def test_fail_closed_empty_answerers(tmp_path):
    svc = ApprovalService(policy="ask", answerers=[], path=tmp_path / "approvals.jsonl")
    rid = svc.request("submit_report", {})["id"]
    r = svc.decide(rid, True, "admin", "越权尝试")
    assert r["status"] == "denied" and r["allow"] is False
    assert "fail-closed" in r["reason"]
    assert svc.list_pending() == []


def test_unauthorized_answerer_fail_closed(tmp_path):
    svc = ApprovalService(policy="ask", answerers=["admin"],
                          path=tmp_path / "approvals.jsonl")
    rid = svc.request("submit_report", {})["id"]
    r = svc.decide(rid, True, "intruder", "冒名决定")
    assert r["status"] == "denied" and r["allow"] is False
    assert "fail-closed" in r["reason"]


def test_policy_never_no_pending(tmp_path):
    svc = ApprovalService(policy="never", answerers=["admin"],
                          path=tmp_path / "approvals.jsonl")
    r = svc.request("submit_report", {})
    assert r["id"] is None and r["status"] == "denied"
    assert svc.list_pending() == []


def test_jsonl_persist_and_reload(tmp_path):
    p = tmp_path / "approvals.jsonl"
    svc1 = ApprovalService(policy="ask", answerers=["admin"], path=p)
    rid = svc1.request("submit_report", {"company": "X"})["id"]

    svc2 = ApprovalService(policy="ask", answerers=["admin"], path=p)
    pending = svc2.list_pending()
    assert any(r["id"] == rid for r in pending)

    # 重载后仍可决定（持久化状态一致）
    r = svc2.decide(rid, True, "admin", "批准")
    assert r["status"] == "allowed"
    assert svc2.list_pending() == []


def test_decide_not_found(svc):
    r = svc.decide("appr-nonexistent", True, "admin", "")
    assert r["status"] == "not_found" and r["allow"] is False
