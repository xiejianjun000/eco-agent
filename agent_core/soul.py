#!/usr/bin/env python3
"""
soul.py — SOUL 接线：加载 profiles 中的 SOUL.md / *_soul.md，解析为运行时可用结构

设计：
  - 主人格：profiles/eco-agent/SOUL.md
      「硬边界」段落      -> 安全层增补（与 prompt_engine 硬编码安全准则合并，硬编码兜底）
      身份/核心人格/沟通风格/座右铭 -> 基础系统提示词（人格层）
  - 角色人格：profiles/agents/<role>_soul.md -> role_swarm 角色 brief 增补
  - 文件缺失/解析失败：回退空结构，调用方使用硬编码兜底，不崩

查找顺序（后者覆盖前者不可用时的兜底）：
  1. $ECO_PROFILES_DIR (若设置)
  2. ~/.eco/profiles/
  3. 本仓 profiles/
"""

import logging
import re
from pathlib import Path

logger = logging.getLogger("soul")

_REPO_PROFILES = Path(__file__).resolve().parent.parent / "profiles"


def _profiles_dirs() -> list[Path]:
    import os
    dirs = []
    env = os.environ.get("ECO_PROFILES_DIR", "").strip()
    if env:
        dirs.append(Path(env).expanduser())
    dirs.append(Path.home() / ".eco" / "profiles")
    dirs.append(_REPO_PROFILES)
    return dirs


def _find_file(rel: str) -> Path | None:
    for d in _profiles_dirs():
        p = d / rel
        if p.exists():
            return p
    return None


def _parse_sections(md: str) -> dict[str, str]:
    """按 '## 标题' 切分 Markdown 段落 -> {标题: 正文}"""
    sections: dict[str, list[str]] = {}
    current = "_header"
    for line in md.splitlines():
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m:
            current = m.group(1).strip()
            sections.setdefault(current, [])
        else:
            sections.setdefault(current, []).append(line)
    return {k: "\n".join(v).strip() for k, v in sections.items()}


class Soul:
    """主人格解析结果"""

    def __init__(self, raw: str = "", source: Path | None = None):
        self.raw = raw
        self.source = source
        self.loaded = bool(raw.strip())
        self.sections = _parse_sections(raw) if self.loaded else {}

    @property
    def hard_boundaries(self) -> str:
        """硬边界段落（进入安全层增补）"""
        return self.sections.get("硬边界", "")

    @property
    def persona_prompt(self) -> str:
        """人格/沟通风格段落 -> 基础系统提示词片段"""
        if not self.loaded:
            return ""
        parts = []
        for key in ("身份", "核心人格", "沟通风格", "知识边界", "座右铭"):
            text = self.sections.get(key, "")
            if text:
                parts.append(f"【{key}】\n{text}")
        return "\n\n".join(parts)


_soul_cache: Soul | None = None


def load_soul(force_reload: bool = False) -> Soul:
    """加载主人格 SOUL.md。缺失时返回空 Soul（loaded=False），调用方回退硬编码。"""
    global _soul_cache
    if _soul_cache is not None and not force_reload:
        return _soul_cache
    path = _find_file("eco-agent/SOUL.md")
    if path is None:
        logger.warning("[soul] SOUL.md 未找到，回退硬编码人格/安全层")
        _soul_cache = Soul()
        return _soul_cache
    try:
        raw = path.read_text(encoding="utf-8")
        _soul_cache = Soul(raw, source=path)
        logger.info(f"[soul] SOUL.md 已加载: {path} "
                    f"(硬边界={'有' if _soul_cache.hard_boundaries else '无'})")
    except OSError as e:
        logger.warning(f"[soul] SOUL.md 读取失败: {e}，回退硬编码")
        _soul_cache = Soul()
    return _soul_cache


def load_agent_soul(role: str) -> str:
    """加载 profiles/agents/<role>_soul.md 全文；缺失返回 ''（回退硬编码 brief）"""
    path = _find_file(f"agents/{role}_soul.md")
    if path is None:
        logger.info(f"[soul] 角色人格文件缺失: agents/{role}_soul.md，使用硬编码 brief")
        return ""
    try:
        text = path.read_text(encoding="utf-8").strip()
        return text
    except OSError as e:
        logger.warning(f"[soul] 角色人格读取失败 {role}: {e}")
        return ""


def _reset_for_test():
    global _soul_cache
    _soul_cache = None
