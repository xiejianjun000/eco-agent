#!/usr/bin/env python3
"""
server/api/skills.py — 技能 API

复用 agent_core.ecoskills.SkillRegistry（~/.eco/ecoskills/index.json）。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query

logger = logging.getLogger("eco.server.skills")

router = APIRouter()


def _registry():
    from agent_core.ecoskills import SkillRegistry

    return SkillRegistry()


@router.get("/skills")
async def list_skills() -> dict:
    reg = _registry()
    skills = reg.list()
    return {"count": len(skills), "skills": skills}


@router.get("/skills/search")
async def search_skills(q: str = Query(..., min_length=1)) -> dict:
    reg = _registry()
    results = reg.search(q)
    return {"query": q, "count": len(results), "skills": results}


@router.get("/skills/{name}")
async def get_skill(name: str) -> dict:
    from fastapi import HTTPException

    reg = _registry()
    skill = reg.get(name)
    if skill is None:
        raise HTTPException(status_code=404, detail="skill not found")
    return skill
