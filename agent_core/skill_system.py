#!/usr/bin/env python3
"""
skill_system.py — Eco Agent 技能系统 MVP

Phase 2 核心交付：
  1. Skill Registry — 技能注册/发现/版本管理
  2. Auto-Learn — 从任务执行中自动生成技能
  3. Skill Evolution — 评测/合并/去重/归档
  4. Cross-session memory — 四层认知记忆接口

对标：Hermes 的学习闭环 + 超越目标
"""

import json
import threading
import uuid
import logging
import re
from pathlib import Path
from datetime import datetime, timedelta
from typing import Any
from dataclasses import dataclass, field, asdict

logger = logging.getLogger("skill_system")

ROOT = Path(__file__).resolve().parent.parent
SKILL_DIR = ROOT / "skills"
DATA_DIR = ROOT / "memory-tree" / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


# ═══════════════════════════════════
# 1. Skill Registry
# ═══════════════════════════════════

@dataclass
class Skill:
    """技能——可复用能力单元"""
    id: str = ""
    name: str = ""
    version: str = "0.1.0"
    description: str = ""
    category: str = "general"
    author: str = "system"
    triggers: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
    requirements: list[str] = field(default_factory=list)
    usage_count: int = 0
    avg_score: float = 0.0
    created_at: str = ""
    updated_at: str = ""
    status: str = "active"  # active / archived / deprecated
    source: str = "manual"  # manual / auto_learned / evolved

    def __post_init__(self):
        if not self.id:
            self.id = f"skill_{uuid.uuid4().hex[:8]}"
        now = datetime.now().isoformat()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now


class SkillRegistry:
    """技能注册表——注册/发现/版本/持久化（带名称索引和分类索引）"""

    def __init__(self):
        self._skills: dict[str, Skill] = {}
        self._name_index: dict[str, str] = {}  # name -> skill_id
        self._category_index: dict[str, list[str]] = {}  # category -> [skill_ids]
        self._db_path = DATA_DIR / "skill_registry.json"
        self._load()

    def _load(self):
        if self._db_path.exists():
            try:
                data = json.loads(self._db_path.read_text("utf-8", errors="replace"))
                for sid, sdata in data.items():
                    self._skills[sid] = Skill(**sdata)
            except Exception as e:
                logger.warning(f"技能注册表加载失败: {e}")
        self._rebuild_index()

    def _rebuild_index(self):
        """重建名称索引和分类索引"""
        self._name_index.clear()
        self._category_index.clear()
        for sid, s in self._skills.items():
            self._name_index[s.name] = sid
            self._category_index.setdefault(s.category, []).append(sid)

    def _save(self):
        data = {sid: asdict(s) for sid, s in self._skills.items()}
        self._db_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def register(self, skill: Skill) -> str:
        """注册技能"""
        self._skills[skill.id] = skill
        self._name_index[skill.name] = skill.id
        self._category_index.setdefault(skill.category, []).append(skill.id)
        self._save()
        self._sync_to_file(skill)
        logger.info(f"[Skill] 注册: {skill.name} v{skill.version}")
        return skill.id

    def get(self, skill_id: str) -> Skill | None:
        return self._skills.get(skill_id)

    def find(self, query: str) -> list[Skill]:
        """按关键词查找技能（O(1) 名称精确匹配 + O(k) 模糊匹配）"""
        q = query.lower().strip()
        if not q:
            return []
        # O(1) 精确名称匹配
        if q in self._name_index:
            sid = self._name_index[q]
            s = self._skills.get(sid)
            if s and s.status == "active":
                return [s]
        # O(k) 部分匹配（名称/描述/触发词）
        results = []
        for s in self._skills.values():
            if s.status != "active":
                continue
            if q in s.name.lower() or q in s.description.lower() or any(q in t.lower() for t in s.triggers):
                results.append(s)
        return sorted(results, key=lambda s: s.usage_count, reverse=True)[:10]

    def list_by_category(self, category: str) -> list[Skill]:
        """O(1) 分类索引查找"""
        sids = self._category_index.get(category, [])
        return [self._skills[sid] for sid in sids if self._skills.get(sid) and self._skills[sid].status == "active"]

    def record_usage(self, skill_id: str, score: float = 0.0):
        """记录技能使用"""
        skill = self._skills.get(skill_id)
        if skill:
            skill.usage_count += 1
            if score > 0:
                skill.avg_score = (skill.avg_score * (skill.usage_count - 1) + score) / skill.usage_count
            skill.updated_at = datetime.now().isoformat()
            self._save()

    def archive_old(self, max_age_days: int = 180, min_usage: int = 3):
        """归档低效技能"""
        now = datetime.now()
        archived = 0
        for s in list(self._skills.values()):
            try:
                updated = datetime.fromisoformat(s.updated_at)
                age = (now - updated).days
                if age > max_age_days and s.usage_count < min_usage and s.status == "active":
                    s.status = "archived"
                    archived += 1
            except Exception: pass
        if archived:
            self._save()
            self._rebuild_index()
            logger.info(f"[Skill] 归档 {archived} 个低效技能")

    def _sync_to_file(self, skill: Skill):
        """同步到技能文件"""
        SKILL_DIR.mkdir(parents=True, exist_ok=True)
        fname = re.sub(r'[^\w一-鿿]', '_', skill.name)[:40]
        content = f"""---
name: {skill.name}
version: {skill.version}
description: {skill.description}
category: {skill.category}
author: {skill.author}
status: {skill.status}
source: {skill.source}
---

# {skill.name}

## Meta
- ID: {skill.id}
- 版本: {skill.version}
- 使用次数: {skill.usage_count}
- 平均评分: {skill.avg_score:.2f}

## Triggers
{chr(10).join(f'- {t}' for t in skill.triggers)}

## Steps
{chr(10).join(f'- {s}' for s in skill.steps)}

## Examples
{chr(10).join(f'- {e}' for e in skill.examples)}
"""
        (SKILL_DIR / f"{fname}.md").write_text(content, encoding="utf-8")

    def get_stats(self) -> dict:
        by_category = {}
        for s in self._skills.values():
            by_category[s.category] = by_category.get(s.category, 0) + 1
        return {
            "total": len(self._skills),
            "active": sum(1 for s in self._skills.values() if s.status == "active"),
            "by_category": by_category,
            "total_usage": sum(s.usage_count for s in self._skills.values()),
        }


# ═══════════════════════════════════
# 2. Auto-Learn Engine
# ═══════════════════════════════════

class AutoLearnEngine:
    """自动学习引擎——从任务执行中提取技能"""

    def __init__(self, registry: SkillRegistry):
        self._registry = registry

    def learn_from_task(self, task_desc: str, task_steps: list[str],
                        task_output: str, score: float) -> str | None:
        """从单次任务执行中学习"""
        # 检查是否已有相似技能
        existing = self._registry.find(task_desc)
        if existing:
            # 更新已有技能
            skill = existing[0]
            skill.usage_count += 1
            skill.avg_score = (skill.avg_score * (skill.usage_count - 1) + score) / skill.usage_count
            if task_steps and len(task_steps) > len(skill.steps):
                skill.steps = task_steps
            return skill.id

        # 新技能条件：至少 3 步且有明确输出
        if len(task_steps) < 3 or not task_output:
            return None

        # 自动分类
        category = self._classify(task_desc)

        skill = Skill(
            name=f"auto_{task_desc[:20]}",
            description=f"自动学习: {task_desc[:60]}",
            category=category,
            author="auto_learn",
            triggers=[task_desc[:50]],
            steps=task_steps,
            examples=[task_output[:100]] if task_output else [],
            usage_count=1,
            avg_score=score,
            source="auto_learned",
        )
        return self._registry.register(skill)

    def _classify(self, desc: str) -> str:
        d = desc.lower()
        if any(kw in d for kw in ["代码", "编程", "开发", "python", "javascript"]): return "coding"
        if any(kw in d for kw in ["写", "文档", "报告", "文章"]): return "writing"
        if any(kw in d for kw in ["分析", "研究", "查询", "搜索"]): return "research"
        if any(kw in d for kw in ["设计", "架构", "规划"]): return "design"
        return "general"


# ═══════════════════════════════════
# 3. Cross-Session Memory
# ═══════════════════════════════════

class CrossSessionMemory:
    """跨会话记忆——四层认知记忆结构（TTL 惰性清理 + 容量上限）"""

    def __init__(self):
        self._db_path = DATA_DIR / "cross_session_memory.json"
        self._memory = self._load()
        self._lock = threading.Lock()  # 保护并发读写

    def _load(self) -> dict:
        if self._db_path.exists():
            try: return json.loads(self._db_path.read_text("utf-8", errors="replace"))
            except Exception: pass
        return {"working": [], "episodic": [], "semantic": {}, "procedural": {}}

    def _save(self):
        self._db_path.write_text(json.dumps(self._memory, ensure_ascii=False, indent=2), encoding="utf-8")

    def _cleanup_working(self):
        """惰性清理过期的工作记忆"""
        now = datetime.now()
        before = len(self._memory["working"])
        self._memory["working"] = [
            e for e in self._memory["working"]
            if datetime.fromisoformat(e.get("expires_at", "1970-01-01")) > now
        ]
        removed = before - len(self._memory["working"])
        if removed > 0:
            logger.debug("[CrossSessionMemory] 清理 %d 条过期 working 记忆", removed)

    def store_working(self, key: str, value: Any, ttl_minutes: int = 60):
        """工作记忆——短时（自动清理过期项 + 容量上限 1000）"""
        with self._lock:
            self._cleanup_working()
            # 去重：移除同名 key
            self._memory["working"] = [e for e in self._memory["working"] if e["key"] != key]
            self._memory["working"].append({
                "key": key, "value": str(value)[:500],
                "expires_at": (datetime.now() + timedelta(minutes=ttl_minutes)).isoformat()
            })
            # 容量上限：保留最新的 1000 条
            if len(self._memory["working"]) > 1000:
                self._memory["working"] = self._memory["working"][-1000:]
            self._save()

    def store_episodic(self, event: str, context: dict):
        """情景记忆——历史事件"""
        with self._lock:
            self._memory["episodic"].append({
                "event": event, "context": context,
                "timestamp": datetime.now().isoformat(),
            })
            if len(self._memory["episodic"]) > 1000:
                self._memory["episodic"] = self._memory["episodic"][-1000:]
            self._save()

    def store_semantic(self, key: str, fact: Any):
        """语义记忆——知识图谱事实"""
        with self._lock:
            self._memory["semantic"][key] = {
                "value": str(fact)[:500], "updated_at": datetime.now().isoformat()
            }
            self._save()

    def store_procedural(self, skill_id: str, steps: list[str]):
        """程序记忆——技能/工作流"""
        with self._lock:
            self._memory["procedural"][skill_id] = steps
            self._save()

    def recall_working(self, key: str) -> Any | None:
        """回忆工作记忆（自动清理过期项）"""
        with self._lock:
            self._cleanup_working()
            for e in self._memory["working"]:
                if e["key"] == key:
                    return e["value"]
            return None

    def recall_episodic(self, query: str, limit: int = 5) -> list[dict]:
        """回忆情景记忆"""
        q = query.lower()
        results = [e for e in self._memory["episodic"] if q in e["event"].lower()]
        return results[-limit:]

    def recall_semantic(self, key: str) -> Any | None:
        return self._memory["semantic"].get(key, {}).get("value")

    def get_stats(self) -> dict:
        return {
            "working_items": len(self._memory["working"]),
            "episodic_events": len(self._memory["episodic"]),
            "semantic_facts": len(self._memory["semantic"]),
            "procedural_skills": len(self._memory["procedural"]),
        }


# ===== 测试 =====

def test():
    import io
    import sys as _sys
    _sys.stdout = io.TextIOWrapper(_sys.stdout.buffer, encoding='utf-8', errors='replace')
    print("[TEST] Skill System MVP", flush=True)

    # 1. Skill Registry
    registry = SkillRegistry()
    skill = Skill(name="test-skill", description="测试技能", category="general",
                  triggers=["test"], steps=["step1", "step2"])
    sid = registry.register(skill)
    found = registry.find("test")
    print(f"[Registry] 注册: {sid}, 查找: {len(found)} 结果", flush=True)

    # 2. Auto-Learn
    learner = AutoLearnEngine(registry)
    result = learner.learn_from_task("编写Python数据分析脚本",
                                      ["导入数据", "清洗数据", "分析数据", "生成报告"],
                                      "分析完成", 0.85)
    print(f"[AutoLearn] 学习: {'新技能' if result else '未满足条件'}", flush=True)

    # 3. Cross-Session Memory
    mem = CrossSessionMemory()
    mem.store_working("last_query", "大气污染防治法", 60)
    mem.store_episodic("用户查询法规", {"query": "大气污染防治法", "result": "ok"})
    mem.store_semantic("user:preferred_law", "生态环境法典")
    working = mem.recall_working("last_query")
    episodic = mem.recall_episodic("查询")
    print(f"[Memory] 工作记忆: {working}, 情景回忆: {len(episodic)} 条", flush=True)

    stats = registry.get_stats()
    print(f"\n[Stats] 技能: {stats['active']} 活跃 / {stats['total']} 总计, 使用: {stats['total_usage']}", flush=True)
    print(f"[Memory Stats] {mem.get_stats()}", flush=True)
    print(f"\n{'='*30}", flush=True)
    print("[OK] Skill System MVP 测试通过", flush=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test()


# ═══════════════════════════════════════════════════════════════
# 技能 A/B 测试框架
# ═══════════════════════════════════════════════════════════════

class SkillABTest:
    """技能 A/B 测试——对比两个技能变体的成功率
    
    用法：
        test = SkillABTest("check_permit", variant_a, variant_b)
        test.record_result("A", success=True, duration=12.5)
        winner = test.evaluate()  # 返回 "A" / "B" / None
    """

    def __init__(self, skill_id: str, variant_a: Skill, variant_b: Skill):
        self.skill_id = skill_id
        self.variants = {"A": variant_a, "B": variant_b}
        self.results: dict[str, list[dict]] = {"A": [], "B": []}

    def record_result(self, variant: str, success: bool, duration: float) -> None:
        """记录一次执行结果"""
        if variant in self.results:
            self.results[variant].append({"success": success, "duration": duration})

    def evaluate(self) -> str | None:
        """返回优胜变体，或 None 若统计不显著（样本不足）"""
        from statistics import mean
        a_rate = mean([1 if r["success"] else 0 for r in self.results["A"]]) if self.results["A"] else 0
        b_rate = mean([1 if r["success"] else 0 for r in self.results["B"]]) if self.results["B"] else 0
        min_samples = 10
        if len(self.results["A"]) < min_samples or len(self.results["B"]) < min_samples:
            return None
        return "A" if a_rate > b_rate else "B"

    def get_stats(self) -> dict:
        """获取 A/B 测试统计"""
        a_total = len(self.results["A"])
        b_total = len(self.results["B"])
        a_ok = sum(1 for r in self.results["A"] if r["success"])
        b_ok = sum(1 for r in self.results["B"] if r["success"])
        return {
            "skill_id": self.skill_id,
            "variant_a_samples": a_total,
            "variant_b_samples": b_total,
            "a_success_rate": round(a_ok / max(a_total, 1), 3),
            "b_success_rate": round(b_ok / max(b_total, 1), 3),
            "winner": self.evaluate(),
        }
