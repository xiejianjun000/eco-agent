#!/usr/bin/env python3
"""门禁3：审批鉴权强化（对应 B3）

decide 端点仅允许本机访问（防 CSRF/越权）。answerer 自报仍需命中授权链，
此处再加 IP 白名单做纵深防御。
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient

from server.api import approvals
from server.app import create_app


def test_require_local_allows_loopback():
    scope = {"type": "http", "client": ("127.0.0.1", 12345)}
    req = Request(scope)
    # 不抛异常即通过
    approvals._require_local(req)


def test_require_local_rejects_remote():
    scope = {"type": "http", "client": ("203.0.113.7", 12345)}
    req = Request(scope)
    with pytest.raises(HTTPException) as ei:
        approvals._require_local(req)
    assert ei.value.status_code == 403


def test_require_local_rejects_no_client():
    scope = {"type": "http", "client": None}
    req = Request(scope)
    with pytest.raises(HTTPException) as ei:
        approvals._require_local(req)
    assert ei.value.status_code == 403


def test_decide_endpoint_pending_shape():
    """冒烟：app 可建、pending 端点返回结构（testclient 本机放行）。"""
    app = create_app()
    with TestClient(app) as c:
        r = c.get("/api/v1/approvals/pending")
        assert r.status_code == 200
        assert "pending" in r.json()
