#!/usr/bin/env python3
"""
agent_core/skill_dir.py — 仓库技能目录扫描器（对标 DSH skill-filesystem 包）

扫描 <repo>/ecoskills/<name>/SKILL.md，解析 DSH 式 frontmatter
（name/description/whenToUse），提供 list/get/match（触发词匹配），
供 chat 按消息相关性注入技能全文。区别于 ecoskills.py：
  - ecoskills.py → 外部技能包安装（manifest.json + SM3 签名信任链）
  - 本模块 → 仓库自带技能的发现与检索（零签名，目录即契约）
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger("eco.skill_dir")

ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = ROOT / "ecoskills"

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.S)


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    meta: dict = {}
    for line in m.group(1).splitlines():
        line = line.strip()
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    return meta, m.group(2)


class SkillDir:
    """单个仓库技能（SKILL.md 目录）。"""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.name = path.name
        self.meta: dict = {}
        self.body = ""
        self._load()

    def _load(self) -> None:
        entry = self.path / "SKILL.md"
        if not entry.is_file():
            logger.warning("技能目录缺少 SKILL.md: %s", self.path)
            return
        self.meta, self.body = _parse_frontmatter(entry.read_text(encoding="utf-8"))
        self.meta.setdefault("name", self.name)
        self.meta.setdefault("description", "")

    def to_dict(self, with_body: bool = False) -> dict:
        d = {"name": self.name, "path": str(self.path), **self.meta}
        if with_body:
            d["body"] = self.body
        return d

    def match(self, text: str) -> int:
        """相关性打分：字符 bigram 重合（免分词，粒度稳定）+ 名称命中加权。"""
        text = str(text or "")

        def _bigrams(s: str) -> set[str]:
            s = re.sub(r"[^\u4e00-\u9fff]", "", str(s))
            return {s[i:i + 2] for i in range(len(s) - 1)}

        score = 0
        if self.name and self.name in text:
            score += 5
        q = _bigrams(text)
        score += 2 * len(q & _bigrams(self.meta.get("description", "")))
        score += len(q & _bigrams(self.body[:600]))
        return score


class SkillDirRegistry:
    """仓库技能目录注册表（懒加载 + 缓存）。"""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root else SKILLS_DIR
        self._skills: dict[str, SkillDir] = {}
        self._loaded = False

    def _scan(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self.root.is_dir():
            return
        for sub in sorted(self.root.iterdir()):
            if sub.is_dir() and (sub / "SKILL.md").is_file():
                try:
                    self._skills[sub.name] = SkillDir(sub)
                except Exception:  # noqa: BLE001
                    logger.exception("技能加载失败: %s", sub)

    def list(self) -> list[dict]:
        self._scan()
        return [s.to_dict() for s in self._skills.values()]

    def get(self, name: str) -> dict | None:
        self._scan()
        s = self._skills.get(name)
        return s.to_dict(with_body=True) if s else None

    def match(self, text: str, top_n: int = 2) -> list[dict]:
        """按消息相关性返回技能（含正文，供注入）。"""
        self._scan()
        scored = [(s.match(text), s) for s in self._skills.values()]
        scored.sort(key=lambda x: -x[0])
        return [s.to_dict(with_body=True) for score, s in scored if score > 0][:top_n]

    def stats(self) -> dict:
        self._scan()
        return {"skills": len(self._skills), "names": sorted(self._skills.keys())}


_registry: SkillDirRegistry | None = None


def get_skill_dir_registry() -> SkillDirRegistry:
    global _registry
    if _registry is None:
        _registry = SkillDirRegistry()
    return _registry
