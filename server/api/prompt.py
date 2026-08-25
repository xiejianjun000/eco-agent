#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
server/api/prompt.py — 提示词组装管理 API（DSH 式模块化提示词）

对标 DSH 的提示词哲学：
- GET  /prompt/overview         查看当前组装全景（片段/阶段/注入/预览）
- POST /prompt/sections         注册/覆盖自定义提示词片段（插件式贡献）
- DELETE /prompt/sections/{id}  移除片段
- POST /prompt/inject           运行时注入提示词（校验 + SM3 审计，拒绝违规注入）
- DELETE /prompt/inject         按来源清理注入
- POST /prompt/persona          切换执法阶段人设（巡查/文书/评查）

全部变更写 SM3 审计链（source=prompt_api），注入内容经 validate_injection
安全校验（试图覆盖安全层/绕过监管的注入直接拒绝）。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from agent_core.prompt_engine import get_prompt_engine

logger = logging.getLogger("eco.server.prompt")

router = APIRouter()


class InjectRequest(BaseModel):
    content: str = Field(..., description="注入的提示词内容（经安全校验）")
    source: str = Field(default="api", description="注入来源标识")
    task_id: str = Field(default="", description="关联任务 ID（审计用）")


class PersonaRequest(BaseModel):
    phase: str = Field(..., description="执法阶段：inspection 巡查 / documentation 文书 / review 评查")


class SectionRequest(BaseModel):
    section_id: str = Field(..., description="片段唯一 ID")
    title: str = Field(..., description="片段标题")
    content: str = Field(..., description="片段内容（静态文本）")
    priority: int | None = Field(default=None, description="组装优先级（越小越靠前，默认 custom=60）")
    source: str = Field(default="api", description="来源标识")


@router.get("/prompt/overview")
async def prompt_overview() -> dict:
    """当前系统提示词组装全景（DSH 式：基础片段 + 阶段 + 注入 + 组装预览）。"""
    return get_prompt_engine().overview()


@router.post("/prompt/sections")
async def register_section(req: SectionRequest) -> dict:
    """注册/覆盖一个自定义提示词片段（插件式贡献，可插拔）。"""
    eng = get_prompt_engine()
    try:
        eng.register_section(req.section_id, req.title, req.content,
                             priority=req.priority, source=req.source)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    eng.audit.append(source=f"prompt_api:{req.source}",
                     content=f"section 注册/覆盖: {req.section_id} ({req.title})",
                     accepted=True, reason="section_registered")
    return {"ok": True, "section_id": req.section_id,
            "sections": eng.list_sections()}


@router.delete("/prompt/sections/{section_id}")
async def unregister_section(section_id: str) -> dict:
    """移除提示词片段。"""
    eng = get_prompt_engine()
    removed = eng.unregister_section(section_id)
    eng.audit.append(source="prompt_api", content=f"section 移除: {section_id}",
                     accepted=True, reason="section_removed")
    return {"ok": removed, "section_id": section_id, "sections": eng.list_sections()}


@router.post("/prompt/inject")
async def inject_prompt(req: InjectRequest) -> dict:
    """运行时注入提示词：validate_injection 安全校验 + SM3 审计。

    违规注入（试图覆盖安全层/解除限制等）直接拒绝并记入审计链。
    """
    eng = get_prompt_engine()
    ok = eng.inject(req.content, source=req.source, task_id=req.task_id)
    if not ok:
        return {"ok": False, "reason": "注入被安全校验拒绝（已写入 SM3 审计链）",
                "injections": eng.list_injections()}
    return {"ok": True, "injections": eng.list_injections()}


@router.delete("/prompt/inject")
async def clear_injections(source: str = Query(default="", description="按来源前缀清理；空=全部")) -> dict:
    """清理运行时注入（按来源前缀或全部）。"""
    eng = get_prompt_engine()
    n = eng.clear_injections(source_prefix=source)
    eng.audit.append(source="prompt_api",
                     content=f"injections 清理: source={source or '*'} count={n}",
                     accepted=True, reason="injections_cleared")
    return {"ok": True, "cleared": n, "injections": eng.list_injections()}


@router.post("/prompt/persona")
async def switch_persona(req: PersonaRequest) -> dict:
    """切换执法阶段人设（巡查/文书/评查，三阶段提示词状态机）。"""
    eng = get_prompt_engine()
    if not eng.switch_phase(req.phase, task_id="prompt_api"):
        raise HTTPException(status_code=400,
                            detail=f"非法阶段: {req.phase}（可选 inspection/documentation/review）")
    return {"ok": True, "phase": eng.phase, "overview": eng.overview()}
