#!/usr/bin/env python3
"""领域专家团 spec 包。import 本包即触发 expert_team._auto_register 注册内置团队。"""
from agent_core.team_specs import law_enforcement, air_source  # noqa: F401

__all__ = ["law_enforcement", "air_source"]
