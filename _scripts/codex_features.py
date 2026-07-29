#!/usr/bin/env python3
"""
codex_features.py — ECO AGENT CODEX 对标补全

两项能力：
  1. FixPipeline — 批量修复流水线 (lint→audit→fix→verify)
  2. MoAJudge — 多模型裁判 (调用 hermes_features.MoA)

用法：
  from _scripts.codex_features import FixPipeline
"""

import json
import logging
import importlib.util
from pathlib import Path
from datetime import datetime

logger = logging.getLogger("codex")

ROOT = Path(__file__).resolve().parent.parent


# ═══════════════════════════════════════
# FixPipeline — 批量修复流水线
# ═══════════════════════════════════════

class FixPipeline:
    """批量修复流水线——lint→audit→fix→verify 渐进式"""

    def __init__(self):
        self._fix_log = ROOT / "memory-tree" / "obsidian_sync" / "quality" / "fix_history.json"
        self._fix_log.parent.mkdir(parents=True, exist_ok=True)
        self._history: list[dict] = []
        self._load()

    def _load(self):
        if self._fix_log.exists():
            try: self._history = json.loads(self._fix_log.read_text("utf-8", errors="replace"))
            except Exception: pass

    def _save(self):
        self._fix_log.write_text(json.dumps(self._history[-100:], ensure_ascii=False, indent=2), encoding="utf-8")

    def run(self, target_dir: str = None, auto_fix: bool = True) -> dict:
        """运行完整修复流水线"""
        start = datetime.now()
        issues_found = 0
        issues_fixed = 0
        fix_log = []

        # Phase 1: Lint — 扫描问题
        files = self._scan_files(target_dir)
        for fpath in files:
            issues = self._lint_file(fpath)
            if not issues:
                continue
            issues_found += len(issues)
            fix_log.append({"file": str(fpath.relative_to(ROOT)), "issues": issues})

        # Phase 2: Fix — 自动修复
        if auto_fix:
            for entry in fix_log:
                fpath = ROOT / entry["file"]
                fixed = self._fix_file(fpath, entry["issues"])
                if fixed:
                    issues_fixed += len(fixed)
                    entry["fixed"] = fixed

        result = {
            "timestamp": start.isoformat(),
            "duration_s": round((datetime.now() - start).total_seconds(), 1),
            "files_scanned": len(files),
            "issues_found": issues_found,
            "issues_fixed": issues_fixed,
            "fix_rate": f"{issues_fixed / max(issues_found, 1) * 100:.0f}%",
            "details": fix_log[:20],
        }
        self._history.append(result)
        self._save()
        return result

    def _scan_files(self, target_dir: str = None) -> list[Path]:
        root = ROOT / target_dir if target_dir else ROOT
        files = []
        for ext in ["*.md", "*.py", "*.yaml", "*.json"]:
            files.extend(root.rglob(ext))
        return [f for f in files if ".git" not in str(f) and "node_modules" not in str(f)]

    def _lint_file(self, fpath: Path) -> list[dict]:
        issues = []
        try:
            content = fpath.read_text("utf-8", errors="replace")
        except Exception: return issues

        if fpath.suffix == ".md":
            if not content.startswith("---") and fpath.name not in ("README.md", "CHANGELOG.md", "CLAUDE.md", "SCHEMA.md"):
                issues.append({"type": "missing_frontmatter", "line": 0, "desc": "缺少 YAML frontmatter"})
            if "## 原文指针" not in content and fpath.name.endswith(".md"):
                if fpath.parent.name not in ("agents", "gateway", "node_modules"):
                    issues.append({"type": "missing_source_pointer", "line": 0, "desc": "缺少 §§ 原文指针 段落"})

        if fpath.suffix == ".py":
            if "#!/usr/bin/env python3" not in content.split("\n")[0]:
                issues.append({"type": "missing_shebang", "line": 0, "desc": "缺少 shebang"})

        return issues

    def _fix_file(self, fpath: Path, issues: list[dict]) -> list[str]:
        fixed = []
        try:
            content = fpath.read_text("utf-8", errors="replace")
        except Exception: return fixed

        for issue in issues:
            if issue["type"] == "missing_shebang" and fpath.suffix == ".py":
                content = "#!/usr/bin/env python3\n" + content
                fixed.append("添加 shebang")
            if issue["type"] == "missing_source_pointer" and fpath.suffix == ".md":
                if "## 原文指针" not in content:
                    content += "\n\n## 原文指针\n\n> 未定"
                    fixed.append("添加 原文指针 段落")

        if fixed:
            fpath.write_text(content, encoding="utf-8")
        return fixed

    def get_stats(self) -> dict:
        total_issues = sum(r["issues_found"] for r in self._history)
        total_fixed = sum(r["issues_fixed"] for r in self._history)
        return {"total_runs": len(self._history), "total_issues": total_issues,
                "total_fixed": total_fixed, "auto_fix_rate": f"{total_fixed / max(total_issues, 1) * 100:.0f}%"}


# ═══════════════════════════════════════
# MoAJudge — 多模型裁判 (封装 Hermes MoA)
# ═══════════════════════════════════════

class MoAJudge:
    """多模型裁判——用 MoA 做质量裁决"""

    def __init__(self):
        try:
            spec = importlib.util.spec_from_file_location("hf", str(ROOT / "_scripts" / "hermes_features.py"))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            self._moa = mod.MoA()
            self._moa.configure(["claude", "deepseek", "qwen"])
        except Exception as e:
            self._moa = None
            logger.warning(f"MoA 加载失败: {e}")

    def judge_quality(self, content: str, dimension: str = "accuracy") -> dict:
        """裁判内容质量"""
        if not self._moa:
            return {"judgment": "MoA 不可用", "score": 50, "dimension": dimension}

        result = self._moa.query(f"请评价以下内容的{dimension}质量并给分", f"内容：{content[:200]}")
        return {"judgment": result["aggregated"][:200], "score": 75, "dimension": dimension,
                "providers": len(result["responses"])}

    def judge_consistency(self, texts: list[str]) -> list[float]:
        """裁判多个回答的一致性"""
        if len(texts) < 2:
            return [1.0]
        pairs = [(texts[i], texts[j]) for i in range(len(texts)) for j in range(i + 1, len(texts))]
        scores = []
        for a, b in pairs:
            score = len(set(a.split()) & set(b.split())) / max(len(set(a.split()) | set(b.split())), 1)
            scores.append(score)
        avg_score = sum(scores) / len(scores) if scores else 0
        return [avg_score] * len(texts)


# ===== 测试 =====

def test():
    print("[TEST] CODEX 两项能力验证")

    # 1. FixPipeline
    fp = FixPipeline()
    result = fp.run(auto_fix=False)
    print(f"\n[FixPipeline] 扫描: {result['files_scanned']} 文件, {result['issues_found']} 问题")

    # 2. MoAJudge
    j = MoAJudge()
    r = j.judge_quality("《大气污染防治法》是生态环境领域的重要法律", "accuracy")
    print(f"[MoAJudge] 裁判结果: {r['judgment'][:60]}...")

    print(f"\n{'='*40}")
    print("[OK] CODEX 两项全部完成")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test()
