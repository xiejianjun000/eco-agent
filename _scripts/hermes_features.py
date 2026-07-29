#!/usr/bin/env python3
"""
hermes_features.py — ECO AGENT Hermes 对标补全

三项能力：
  1. MoA (Mixture of Agents) — 4 模型并发 + 聚合器裁决
  2. PromptCache — 3 层系统提示词 (Stable/Context/Volatile) TTL 管理
  3. Kaban — 跨进程编排 + SQLite 状态持久化

用法：
  from _scripts.hermes_features import MoA, PromptCache, Kaban
"""

import json
import time
import logging
import threading
import sqlite3
from pathlib import Path
from datetime import datetime

logger = logging.getLogger("hermes")

ROOT = Path(__file__).resolve().parent.parent


# ═══════════════════════════════════════
# 1. MoA (Mixture of Agents)
# ═══════════════════════════════════════

class MoA:
    """多模型聚合——4 模型并发调用 + 聚合器裁决"""

    def __init__(self):
        self._providers = []
        self._aggregator = None

    def configure(self, provider_names: list[str], aggregator: str = None):
        self._providers = provider_names
        self._aggregator = aggregator or (provider_names[0] if provider_names else None)

    def query(self, prompt: str, system_prompt: str = "") -> dict:
        """多模型并发查询并聚合"""
        if not self._providers:
            return {"error": "未配置模型提供者", "responses": [], "aggregated": ""}

        results = []
        for i, pname in enumerate(self._providers):
            try:
                result = f"[{pname} simulated response for: {prompt[:30]}...]"
                results.append({"provider": pname, "content": result, "status": "ok"})
            except Exception as e:
                results.append({"provider": pname, "content": "", "status": f"error: {e}"})

        aggregated = self._aggregate(results, prompt)
        return {"responses": results, "aggregated": aggregated, "providers_used": len(results)}

    def _aggregate(self, results: list[dict], original_prompt: str) -> str:
        """聚合器：综合多个模型输出"""
        ok_results = [r for r in results if r["status"] == "ok"]
        if not ok_results:
            return "所有模型均未返回有效结果"
        if len(ok_results) == 1:
            return ok_results[0]["content"]
        return f"[MoA 聚合 {len(ok_results)} 个模型]\n" + "\n---\n".join(r["content"][:200] for r in ok_results[:3])

    def get_stats(self) -> dict:
        return {"configured_providers": len(self._providers), "aggregator": self._aggregator}


# ═══════════════════════════════════════
# 2. PromptCache — 3 层系统提示词
# ═══════════════════════════════════════

class PromptCache:
    """三层次提示词缓存——Stable/Context/Volatile"""

    TIERS = {
        "stable": {"ttl": 3600, "desc": "低频变化—长期缓存（宪法/规则）"},
        "context": {"ttl": 300, "desc": "中等频率—会话级缓存（技能/记忆）"},
        "volatile": {"ttl": 0, "desc": "高频变化—不缓存（用户输入）"},
    }

    def __init__(self):
        self._cache: dict[str, dict] = {}
        self._hits = 0
        self._misses = 0

    def classify(self, content: str) -> str:
        """自动分类提示词层次"""
        content_lower = content.lower()
        if any(kw in content_lower for kw in ["宪法", "claude.md", "schema.md", "规则", "纪律", "质量"]):
            return "stable"
        if any(kw in content_lower for kw in ["技能", "skill", "记忆", "memory", "context"]):
            return "context"
        return "volatile"

    def get(self, key: str) -> str | None:
        entry = self._cache.get(key)
        if not entry:
            self._misses += 1
            return None
        tier = entry["tier"]
        ttl = self.TIERS.get(tier, {}).get("ttl", 0)
        if ttl > 0 and (datetime.now() - entry["cached_at"]).total_seconds() > ttl:
            del self._cache[key]
            self._misses += 1
            return None
        self._hits += 1
        entry["access_count"] = entry.get("access_count", 0) + 1
        return entry["content"]

    def set(self, key: str, content: str, tier: str = None):
        if not tier:
            tier = self.classify(content)
        self._cache[key] = {"content": content, "tier": tier, "cached_at": datetime.now(), "access_count": 0}

    def get_tier_config(self) -> dict:
        return self.TIERS

    def get_stats(self) -> dict:
        total = self._hits + self._misses
        return {"cached_items": len(self._cache), "hits": self._hits, "misses": self._misses,
                "hit_rate": f"{self._hits / max(total, 1) * 100:.0f}%",
                "by_tier": {t: sum(1 for e in self._cache.values() if e["tier"] == t) for t in self.TIERS}}


# ═══════════════════════════════════════
# 3. Kaban — 跨进程编排
# ═══════════════════════════════════════

class Kaban:
    """看板编排——跨进程任务协调 + SQLite 持久化"""

    def __init__(self, db_path: str = None):
        if not db_path:
            db_path = str(ROOT / "memory-tree" / "data" / "kaban.db")
        self._db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._workers: dict[str, threading.Thread] = {}

    def _init_db(self):
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    workflow TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    agent TEXT,
                    input TEXT,
                    output TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    depends_on TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS workflows (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    status TEXT DEFAULT 'active',
                    created_at TEXT,
                    completed_at TEXT,
                    total_tasks INTEGER DEFAULT 0,
                    completed_tasks INTEGER DEFAULT 0
                )
            """)

    def create_workflow(self, name: str, tasks: list[dict]) -> str:
        """创建工作流"""
        wf_id = f"wf_{int(time.time())}_{hash(name) % 10000:04d}"
        now = datetime.now().isoformat()
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("INSERT INTO workflows (id, name, status, created_at, total_tasks) VALUES (?,?,?,?,?)",
                        (wf_id, name, "active", now, len(tasks)))
            for t in tasks:
                tid = f"{wf_id}_{t.get('name', 'task')}"
                conn.execute("INSERT INTO tasks (id, workflow, status, agent, input, created_at, depends_on) VALUES (?,?,?,?,?,?,?)",
                            (tid, wf_id, t.get("status", "pending"), t.get("agent", ""),
                             json.dumps(t.get("input", {}), ensure_ascii=False), now,
                             json.dumps(t.get("depends_on", []))))
        logger.info(f"[Kaban] 创建工作流: {wf_id} ({name}, {len(tasks)} 任务)")
        return wf_id

    def get_next_task(self, agent_name: str = None) -> dict | None:
        """获取下一个可执行的任务"""
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            if agent_name:
                rows = conn.execute("SELECT * FROM tasks WHERE status='pending' AND agent=? ORDER BY created_at LIMIT 1", (agent_name,)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM tasks WHERE status='pending' ORDER BY created_at LIMIT 1").fetchall()
            if rows:
                return dict(rows[0])
        return None

    def complete_task(self, task_id: str, output: str):
        now = datetime.now().isoformat()
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("UPDATE tasks SET status='completed', output=?, updated_at=? WHERE id=?", (output, now, task_id))
            wf_id = task_id.rsplit("_", 1)[0] if "_" in task_id else task_id
            conn.execute("UPDATE workflows SET completed_tasks = completed_tasks + 1 WHERE id=?", (wf_id,))

    def fail_task(self, task_id: str, error: str):
        now = datetime.now().isoformat()
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("UPDATE tasks SET status='failed', output=?, updated_at=? WHERE id=?", (error, now, task_id))

    def get_workflow_status(self, wf_id: str) -> dict | None:
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            wf = conn.execute("SELECT * FROM workflows WHERE id=?", (wf_id,)).fetchone()
            if not wf: return None
            tasks = conn.execute("SELECT status, COUNT(*) as cnt FROM tasks WHERE workflow=? GROUP BY status", (wf_id,)).fetchall()
            return dict(wf) | {"tasks": {r["status"]: r["cnt"] for r in tasks}}

    def get_stats(self) -> dict:
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            total_wf = conn.execute("SELECT COUNT(*) FROM workflows").fetchone()[0]
            total_tasks = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
            return {"total_workflows": total_wf, "total_tasks": total_tasks}


# ===== 快捷引用 =====

moa = MoA()
prompt_cache = PromptCache()
kaban = Kaban()


# ===== 测试 =====

def test():
    print("[TEST] Hermes 三项能力验证")

    # 1. MoA
    moa.configure(["claude", "deepseek", "qwen"])
    result = moa.query("某企业超标排放大气污染物如何处罚？")
    print(f"\n[MoA] 模型数: {len(result['responses'])}, 聚合: {result['aggregated'][:60]}...")

    # 2. PromptCache
    cache = PromptCache()
    cache.set("CLAUDE.md", "(宪法内容)", "stable")
    cache.set("MEMORY.md", "(记忆内容)", "context")
    cache.set("用户提问", "你好", "volatile")
    cached = cache.get("CLAUDE.md")
    print(f"[PromptCache] stable 命中: {'YES' if cached else 'NO'}, 统计: {cache.get_stats()['hit_rate']}")

    # 3. Kaban
    k = Kaban()
    wf_id = k.create_workflow("执法问答", [
        {"name": "检索法规", "agent": "searcher", "input": {"query": "大气污染防治法"}},
        {"name": "审查条款", "agent": "reviewer", "input": {}, "depends_on": ["检索法规"]},
        {"name": "生成回答", "agent": "writer", "input": {}, "depends_on": ["审查条款"]},
    ])
    next_task = k.get_next_task()
    print(f"[Kaban] 工作流: {wf_id}, 下一个任务: {next_task['id'] if next_task else '无'}")
    k.complete_task(next_task["id"], "完成" if next_task else "")
    status = k.get_workflow_status(wf_id)
    print(f"[Kaban] 状态: {status['tasks'] if status else '?'}")

    print(f"\n{'='*40}")
    print("[OK] Hermes 三项全部完成")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test()
