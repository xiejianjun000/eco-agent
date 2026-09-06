#!/usr/bin/env python3
"""
server/api/workspaces.py — 工作空间 API

工作空间 = ECO_WORKSPACE_DIR/workspaces/ 下的子文件夹（文件夹驱动真源）。
侧边栏/输入栏的工作空间选择器从这里取列表，新建即建目录。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from server.api.files import _workspace_root

logger = logging.getLogger("eco.server.workspaces")

router = APIRouter()


class WorkspaceCreate(BaseModel):
    name: str = Field(..., description="工作空间名（新建为 workspaces/ 子文件夹）")


def _clean_name(name: str) -> str:
    """名称清洗：去首尾空白、限长 50；含路径分隔符或 .. 的名字视为非法（返回空）。"""
    n = (name or "").strip()
    if any(c in n for c in ("/", "\\")) or ".." in n:
        return ""
    return n[:50].strip()


def _workspaces_dir(create: bool = False):
    d = _workspace_root() / "workspaces"
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


@router.get("/workspaces")
def list_workspaces() -> dict:
    """工作空间列表：workspaces/ 下的子文件夹，按名称排序；目录不存在返回空。"""
    d = _workspaces_dir()
    if not d.is_dir():
        return {"workspaces": []}
    names = sorted(p.name for p in d.iterdir() if p.is_dir())
    return {"workspaces": [{"id": n, "name": n} for n in names]}


@router.post("/workspaces")
def create_workspace(body: WorkspaceCreate) -> dict:
    """新建工作空间（建子文件夹）：名称为空/清洗后为空 400，已存在 409。"""
    name = _clean_name(body.name)
    if not name:
        raise HTTPException(status_code=400, detail="工作空间名为空或非法")
    d = _workspaces_dir(create=True) / name
    if d.exists():
        raise HTTPException(status_code=409, detail=f"工作空间已存在：{name}")
    d.mkdir(parents=True)
    return {"ok": True, "id": name, "name": name}
