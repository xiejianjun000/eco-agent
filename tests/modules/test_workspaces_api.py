#!/usr/bin/env python3
"""tests/modules/test_workspaces_api.py — 工作空间 API（文件夹驱动真源）测试

覆盖：空目录返回空列表；POST 创建后 GET 可见；POST 同名 409；非法名 400。
ECO_WORKSPACE_DIR monkeypatch 到 tmp_path，不碰真实工作区。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from server.api import workspaces as ws_mod  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ECO_WORKSPACE_DIR", str(tmp_path))
    app = FastAPI()
    app.include_router(ws_mod.router, prefix="/api/v1")
    with TestClient(app) as c:
        yield c


def test_empty_dir_returns_empty_list(client):
    r = client.get("/api/v1/workspaces")
    assert r.status_code == 200
    assert r.json() == {"workspaces": []}


def test_create_then_list(client):
    r = client.post("/api/v1/workspaces", json={"name": "娄底市大气监测"})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "id": "娄底市大气监测", "name": "娄底市大气监测"}
    r = client.get("/api/v1/workspaces")
    assert [w["name"] for w in r.json()["workspaces"]] == ["娄底市大气监测"]


def test_create_duplicate_returns_409(client):
    client.post("/api/v1/workspaces", json={"name": "水质分析"})
    r = client.post("/api/v1/workspaces", json={"name": "水质分析"})
    assert r.status_code == 409


@pytest.mark.parametrize("bad", ["../x", "", "   ", ".."])
def test_create_invalid_name_returns_400(client, bad):
    r = client.post("/api/v1/workspaces", json={"name": bad})
    assert r.status_code == 400


def test_list_sorted_by_name(client):
    for n in ["丙", "甲", "乙"]:
        client.post("/api/v1/workspaces", json={"name": n})
    r = client.get("/api/v1/workspaces")
    assert [w["name"] for w in r.json()["workspaces"]] == sorted(["丙", "甲", "乙"])
