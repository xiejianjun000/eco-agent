#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
agent_core/prompt_sections.py — DSH 式模块化系统提示词组装注册表
=================================================================

DSH 的提示词哲学：提示词不是一段固定文本，而是一组可插拔、可排序、
可来源溯源的"提示词片段"（Prompt Section），由各方按优先级贡献，
运行时按序组装。

本模块提供：
- PromptSection：片段数据类（id/title/content/priority/source/enabled）
- PromptSectionRegistry：注册/注销/列表/组装
- PRIORITY：标准优先级常量（安全层永远第一，注入永远最后）

content 支持静态字符串或零参 callable（动态片段，组装时求值），
例如"阶段预设"片段跟随状态机切换实时变化，无需手工刷新注册表。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

# ─── 标准优先级（越小越靠前）──────────────────────────────────

PRIORITY = {
    "safety": 0,        # 安全准则（硬编码 + SOUL 硬边界）——首位不可动摇
    "persona": 10,      # 人设 / 核心身份（SOUL 人格层）
    "tool_guidance": 30,  # 工具指南（能力清单 / 已挂载 MCP）
    "phase": 35,        # 执法阶段状态机（巡查/文书/评查）——保持旧版组装顺序（工具能力在前）
    "rules": 25,        # 领域规则与边界（法典注入、落盘纪律等）
    "context": 40,      # 动态上下文（日期/工作区/模型/阶段等运行时信息）
    "skill": 45,        # 技能注入（触发词匹配的 ecoskills）
    "lessons": 50,      # 历史经验（自愈闭环教训注入）
    "custom": 60,       # 插件/业务自定义片段
    "injection": 90,    # 运行时人工注入（校验+审计后追加）
}


@dataclass
class PromptSection:
    """单个提示词片段。content 为 str 或 callable() -> str。"""

    section_id: str
    title: str
    content: str | Callable[[], str]
    priority: int = PRIORITY["custom"]
    source: str = "unknown"
    enabled: bool = True

    def render(self) -> str:
        """求值片段内容（callable 动态求值，失败降级空串）。"""
        try:
            text = self.content() if callable(self.content) else self.content
        except Exception:  # noqa: BLE001 — 单片段失败不阻断整体组装
            text = ""
        return text.strip()


class PromptSectionRegistry:
    """提示词片段注册表：register/unregister/list/assemble。

    同名 section_id 重复 register 视为更新（覆盖内容与元数据）——
    契合 DSH"插件贡献提示词片段"的语义：插件重载即片段刷新。
    """

    def __init__(self) -> None:
        self._sections: dict[str, PromptSection] = {}

    def register(self, section_id: str, title: str,
                 content: str | Callable[[], str],
                 priority: int = PRIORITY["custom"],
                 source: str = "unknown", enabled: bool = True) -> PromptSection:
        if not section_id or not isinstance(section_id, str):
            raise ValueError("section_id 必须为非空字符串")
        sec = PromptSection(section_id=section_id, title=title, content=content,
                            priority=priority, source=source, enabled=enabled)
        self._sections[section_id] = sec
        return sec

    def unregister(self, section_id: str) -> bool:
        return self._sections.pop(section_id, None) is not None

    def get(self, section_id: str) -> PromptSection | None:
        return self._sections.get(section_id)

    def list(self, include_disabled: bool = False) -> list[PromptSection]:
        """按 (priority, section_id) 稳定排序。"""
        secs = list(self._sections.values())
        if not include_disabled:
            secs = [s for s in secs if s.enabled]
        return sorted(secs, key=lambda s: (s.priority, s.section_id))

    def count(self) -> int:
        return len(self._sections)

    def render_parts(self) -> list[dict]:
        """组装为结构化片段清单（含标题，供检查/调试/审计展示）。"""
        out = []
        for s in self.list():
            text = s.render()
            if text:
                out.append({"section_id": s.section_id, "title": s.title,
                            "content": text, "priority": s.priority, "source": s.source})
        return out

    def assemble(self, header: bool = True) -> str:
        """组装完整文本：按优先级拼接，空片段跳过。

        header=True 时以「title」作为每段标题行（无标题时裸文本）。
        """
        parts = []
        for s in self.list():
            text = s.render()
            if not text:
                continue
            parts.append(f"【{s.title}】\n{text}" if header and s.title else text)
        return "\n\n".join(parts)

    def clear(self, source_prefix: str = "") -> int:
        """清空全部（或按来源前缀清理）片段，返回清理条数。"""
        before = len(self._sections)
        if source_prefix:
            self._sections = {k: v for k, v in self._sections.items()
                              if not v.source.startswith(source_prefix)}
        else:
            self._sections = {}
        return before - len(self._sections)


_sections: PromptSectionRegistry | None = None


def get_prompt_sections() -> PromptSectionRegistry:
    """进程级提示词片段注册表单例。"""
    global _sections
    if _sections is None:
        _sections = PromptSectionRegistry()
    return _sections


def _reset_sections_for_test() -> None:
    global _sections
    _sections = None
