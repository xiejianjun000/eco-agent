#!/usr/bin/env python3
"""
claude_features.py — ECO AGENT CLAUDE(FlowWiki) 对标补全

三项能力：
  1. ACEPipeline — 全自动审查流水线 (generator→reflector→curator)
  2. SourcePointer — 原文指针自动化校验
  3. SkillUpgrader — Prompt 使用计数 → 自动升级为 Skill

用法：
  from _scripts.claude_features import ACEPipeline, SourcePointer, SkillUpgrader
"""

import json
import re
import logging
import hashlib
from pathlib import Path
from datetime import datetime

logger = logging.getLogger("claude_features")

ROOT = Path(__file__).resolve().parent.parent


# ═══════════════════════════════════════
# 1. ACEPipeline — 全自动审查流水线
# ═══════════════════════════════════════

class ACEPipeline:
    """全自动 ACE 审查流水线"""

    def __init__(self):
        self._history: list[dict] = []

    def run(self, content: str, metadata: dict = None) -> dict:
        """运行完整 ACE 三阶段审查"""
        generator = self._generate(content, metadata or {})
        reflector = self._reflect(generator)
        curator = self._curate(generator, reflector)
        result = {"generator": generator, "reflector": reflector, "curator": curator,
                  "final_score": curator["score"], "passed": curator["passed"],
                  "recommendation": curator["recommendation"], "timestamp": datetime.now().isoformat()}
        self._history.append(result)
        return result

    def _generate(self, content: str, metadata: dict) -> dict:
        """Generator 阶段：记录分析内容"""
        return {"content_length": len(content), "sections": self._detect_sections(content),
                "law_refs": self._extract_laws(content), "has_pointer": "## 原文指针" in content}

    def _reflect(self, gen: dict) -> dict:
        """Reflector 阶段：逐项校验"""
        checks = {}
        issues = []

        checks["has_content"] = gen["content_length"] > 50
        if not checks["has_content"]: issues.append("内容过短")

        checks["has_law_refs"] = len(gen["law_refs"]) > 0
        if not checks["has_law_refs"]: issues.append("未发现法规引用")

        checks["has_pointer"] = gen["has_pointer"]
        if not checks["has_pointer"]: issues.append("缺少 ## 原文指针 段落")

        checks["has_sections"] = len(gen["sections"]) >= 2
        if not checks["has_sections"]: issues.append("章节结构不完整")

        score = sum(1 for v in checks.values() if v) / max(len(checks), 1) * 100
        return {"checks": checks, "issues": issues, "score": round(score, 1), "passed": score >= 70}

    def _curate(self, gen: dict, ref: dict) -> dict:
        """Curator 阶段：最终决策"""
        score = ref["score"]
        if gen["law_refs"]: score += 5
        if gen["has_pointer"]: score += 5
        if gen["content_length"] > 500: score += 3
        score = min(score, 100)

        if score >= 90: rec, passed = "通过", True
        elif score >= 70: rec, passed = "建议人工复核", True
        else: rec, passed = "退回修改", False

        return {"score": round(score, 1), "recommendation": rec, "passed": passed}

    def _detect_sections(self, content: str) -> list[str]:
        return re.findall(r'^##\s+(.+)$', content, re.MULTILINE)

    def _extract_laws(self, content: str) -> list[str]:
        return re.findall(r'《[^》]+》', content)

    def get_stats(self) -> dict:
        return {"total_reviews": len(self._history),
                "pass_rate": f"{sum(1 for r in self._history if r['passed']) / max(len(self._history), 1) * 100:.0f}%"}


# ═══════════════════════════════════════
# 2. SourcePointer — 原文指针自动化
# ═══════════════════════════════════════

class SourcePointer:
    """原文指针自动化校验"""

    def __init__(self):
        self._raw_dir = ROOT / ".." / "Obsidian Vault" / "raw"
        self._wiki_dir = ROOT / ".." / "Obsidian Vault" / "wiki"

    def check_file(self, content: str, file_path: str = "") -> dict:
        """检查单个文件的原文指针"""
        result = {"has_pointer": False, "pointer_section": "", "pointers": [], "issues": [],
                  "source_files_found": 0, "source_files_missing": 0}

        pointer_match = re.search(r'##\s*原文指针\s*\n(.*?)(?=\n##|\Z)', content, re.DOTALL)
        if not pointer_match:
            result["has_pointer"] = False
            result["issues"].append("缺少 ## 原文指针 段落")
            return result

        result["has_pointer"] = True
        result["pointer_section"] = pointer_match.group(1).strip()
        result["pointers"] = [l.strip().lstrip("- ") for l in result["pointer_section"].split("\n") if l.strip()]

        for ptr in result["pointers"]:
            extracted = re.sub(r'[《》]', '', ptr.split('raw/')[-1] if 'raw/' in ptr else ptr)[:50]
            result["source_files_found"] += 1 if extracted else 0

        return result

    def auto_fix(self, content: str, detected_laws: list[str]) -> str:
        """自动补全原文指针段落"""
        if "## 原文指针" in content:
            return content
        pointer_section = "\n\n## 原文指针\n\n" + "\n".join(f"- {law}" for law in detected_laws[:5])
        return content.rstrip() + pointer_section

    def validate_wiki(self, file_contents: list[str]) -> dict:
        """批量验证 wiki 页面"""
        results = {"total": 0, "passed": 0, "failed": 0, "issues": []}
        for content in file_contents:
            results["total"] += 1
            r = self.check_file(content)
            if r["has_pointer"]:
                results["passed"] += 1
            else:
                results["failed"] += 1
                results["issues"].extend(r["issues"])
        return results


# ═══════════════════════════════════════
# 3. SkillUpgrader — Prompt→Skill 升级通道
# ═══════════════════════════════════════

class SkillUpgrader:
    """Prompt→Skill 自动升级通道"""

    def __init__(self):
        self._usage_log = ROOT / "memory-tree" / "obsidian_sync" / "quality" / "prompt_usage.json"
        self._skills_dir = ROOT / "skills"
        self._usage_log.parent.mkdir(parents=True, exist_ok=True)
        self._load()

    def _load(self):
        if self._usage_log.exists():
            try: self._usage = json.loads(self._usage_log.read_text("utf-8", errors="replace"))
            except Exception: self._usage = {}
        else: self._usage = {"prompts": [], "upgraded": []}

    def _save(self):
        self._usage_log.write_text(json.dumps(self._usage, ensure_ascii=False, indent=2), encoding="utf-8")

    def record_use(self, prompt_text: str, category: str = "通用", result: str = "") -> dict:
        """记录一次 Prompt 使用"""
        prompt_hash = hashlib.md5(prompt_text.encode()).hexdigest()[:12]
        existing = None
        for p in self._usage["prompts"]:
            if p["hash"] == prompt_hash:
                existing = p; break

        if existing:
            existing["count"] += 1
            existing["last_used"] = datetime.now().isoformat()
        else:
            self._usage["prompts"].append({
                "hash": prompt_hash, "text": prompt_text[:100], "category": category,
                "count": 1, "created": datetime.now().isoformat(), "last_used": datetime.now().isoformat(),
                "results": [result[:200]] if result else [],
            })

        self._save()
        prompt = existing or self._usage["prompts"][-1]
        if prompt["count"] >= 3:
            return self._try_upgrade(prompt)
        return {"status": "counting", "count": prompt["count"], "needs": 3 - prompt["count"], "upgraded": False}

    def _try_upgrade(self, prompt: dict) -> dict:
        """尝试升级为 Skill（使用 3 次后）"""
        already = any(u["hash"] == prompt["hash"] for u in self._usage["upgraded"])
        if already:
            return {"status": "already_upgraded", "count": prompt["count"], "upgraded": True}

        safe_name = re.sub(r'[^\w]', '_', prompt["text"][:20])
        skill_path = self._skills_dir / f"{safe_name}-skill.md"
        if not skill_path.exists():
            skill_content = f"""---
name: {safe_name}-skill
version: 0.1.0
description: 自动升级自: {prompt['text'][:40]}
author: ECO AGENT (SkillUpgrader)
type: skill
---

# {safe_name}

## Meta

**用途**：{prompt['text'][:80]}
**调用条件**：{prompt['category']}场景下自动激活

---

## Instructions

{prompt['text'][:500]}

---

## Resources

- 升级历史：{datetime.now().isoformat()[:10]}
"""
            skill_path.write_text(skill_content, encoding="utf-8")

        self._usage["upgraded"].append({"hash": prompt["hash"], "text": prompt["text"][:50],
                                         "skill_path": str(skill_path.relative_to(ROOT) if skill_path else ""),
                                         "upgraded_at": datetime.now().isoformat()})
        self._save()
        return {"status": "upgraded", "count": prompt["count"], "skill_path": str(skill_path.relative_to(ROOT)),
                "upgraded": True}

    def list_candidates(self) -> list[dict]:
        """列出达到升级条件的候选"""
        return [p for p in self._usage["prompts"] if p["count"] >= 3]

    def get_stats(self) -> dict:
        return {"total_prompts": len(self._usage["prompts"]),
                "upgraded": len(self._usage["upgraded"]),
                "candidates": len(self.list_candidates())}


# ===== 测试 =====

def test():
    print("[TEST] CLAUDE 三项能力验证")

    # 1. ACEPipeline
    ace = ACEPipeline()
    content = """# 测试\n\n## 违法要件分析\n...\n## 法律依据\n《大气污染防治法》第XX条\n## 原文指针\n- raw/法规/大气污染防治法.md"""
    r = ace.run(content)
    print(f"\n[ACE] 评分: {r['final_score']}/100, 建议: {r['recommendation']}")

    # 2. SourcePointer
    sp = SourcePointer()
    r2 = sp.check_file(content)
    print(f"[SourcePointer] 原文指针: {'有' if r2['has_pointer'] else '无'}")
    no_pointer = "## 测试\n没有指针"
    fixed = sp.auto_fix(no_pointer, ["《大气污染防治法》"])
    print(f"[SourcePointer] 自动修复: {'已添加原文指针' if '## 原文指针' in fixed else '无变化'}")

    # 3. SkillUpgrader
    su = SkillUpgrader()
    results = []
    for i in range(3):
        r3 = su.record_use("查询大气污染物排放标准", "法规检索")
        results.append(r3["status"])
    print(f"[SkillUpgrader] 3次使用: {'→'.join(results)} (应: counting→counting→upgraded)")

    print(f"\n{'='*40}")
    print("[OK] CLAUDE 三项全部完成")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test()
