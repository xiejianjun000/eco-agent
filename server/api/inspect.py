"""
server/api/inspect.py — Inspect 契约查询 API（对标 DSH Inspect Provider）

GET /api/v1/inspect/list              全目录
GET /api/v1/inspect/query?kind=&name= 精确查询
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query

from agent_core import inspect as inspect_mod

logger = logging.getLogger("eco.api.inspect")
router = APIRouter()


@router.get("/inspect/list")
async def inspect_list() -> dict:
    return inspect_mod.catalog()


@router.get("/inspect/query")
async def inspect_query(kind: str = Query(..., description="services/plugins/tools/slots"),
                        name: str = Query(..., description="条目名")) -> dict:
    return inspect_mod.query(kind, name)
