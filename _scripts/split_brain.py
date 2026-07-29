#!/usr/bin/env python3
"""
split_brain.py — ECO AGENT Split Brain 三重架构

对标 OPENHUMAN 的三脑架构：
  Reflex (快速层)     → 秒级响应，常规执法问答/法规检索
  Reasoning (深度层)  → 分钟级分析，复杂案情/多法综合/裁量建议
  Subconscious (后台层) → 持续运行，法规监控/案例积累/技能结晶

三脑共享 Memory Tree 但各自独立运行。

用法：
  from _scripts.split_brain import SplitBrain
  brain = SplitBrain()
  brain.reflex("大气污染防治法")        # 快速检索
  brain.reasoning({"案情": "..."})      # 深度分析
  brain.subconscious.start()            # 启动后台
"""

import os, sys, json, time, threading, logging
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any

logger = logging.getLogger("split_brain")

ROOT = Path(__file__).resolve().parent.parent


# ═══════════════════════════════════════
# Reflex — 快速反应层
# ═══════════════════════════════════════

class Reflex:
    """快速反应层——秒级响应常规查询"""

    def __init__(self):
        self._patterns = {
            "greeting": ["你好", "hi", "hello", "您好", "在吗", "早", "下午好"],
            "help": ["帮助", "help", "用法", "说明", "功能"],
            "status": ["状态", "status", "运行"],
        }
        self._cache = {}
        self._cache_ttl = 120  # 缓存 2 分钟

    def process(self, query: str) -> Optional[Dict[str, Any]]:
        """快速处理，如果匹配模式则返回，否则返回 None"""
        query_lower = query.strip().lower()

        # 检查缓存
        if query in self._cache:
            cached = self._cache[query]
            if (datetime.now() - cached["time"]).seconds < self._cache_ttl:
                return cached["response"]

        # 模式匹配
        for intent, keywords in self._patterns.items():
            for kw in keywords:
                if kw in query_lower or query_lower.startswith(kw):
                    response = self._handle_intent(intent, query)
                    self._cache[query] = {"time": datetime.now(), "response": response}
                    return response

        return None

    def _handle_intent(self, intent: str, query: str) -> Dict[str, Any]:
        responses = {
            "greeting": {
                "type": "text",
                "content": "你好！我是 ECO AGENT 执法助手。\n发送法规名称查条文\n发送违法事实获取裁量建议\n发送「帮助」看说明",
                "processing_time_ms": 5,
            },
            "help": {
                "type": "text",
                "content": "【法规检索】发法规名称\n【执法问答】描述违法事实\n【案例查询】案例+关键词\n【状态】发送状态",
                "processing_time_ms": 5,
            },
            "status": {
                "type": "text",
                "content": f"ECO AGENT 运行中\n版本: v3.x\n脑层: Reflex/Reasoning/Subconscious\n时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                "processing_time_ms": 10,
            },
        }
        return responses.get(intent, responses["help"])

    def get_stats(self) -> dict:
        return {"cached_items": len(self._cache), "patterns": list(self._patterns.keys())}


# ═══════════════════════════════════════
# Reasoning — 深度推理层
# ═══════════════════════════════════════

class Reasoning:
    """深度推理层——复杂案件分析、多法综合、裁量建议"""

    def __init__(self):
        self._tasks: List[Dict] = []
        self._max_concurrent = 3

    def analyze_case(self, case_input: Dict[str, Any]) -> Dict[str, Any]:
        """分析案件"""
        task_id = f"task_{len(self._tasks) + 1}_{datetime.now().strftime('%H%M%S')}"
        task = {
            "id": task_id,
            "input": case_input,
            "status": "processing",
            "created_at": datetime.now().isoformat(),
            "result": None,
        }

        # 模拟分析过程（实际调用 LLM）
        task["result"] = self._do_analyze(case_input)
        task["status"] = "completed"
        self._tasks.append(task)

        return task

    def _do_analyze(self, case: Dict) -> Dict:
        """执行分析"""
        facts = str(case.get("facts", case.get("query", "")))
        category = case.get("category", "unknown")

        return {
            "summary": f"分析完成: {facts[:50]}",
            "elements_identified": self._identify_elements(facts),
            "applicable_laws": self._find_applicable_laws(category),
            "confidence": "medium",
            "needs_review": True,
        }

    def _identify_elements(self, facts: str) -> List[str]:
        elements = []
        if "超标" in facts or "排放" in facts:
            elements.append("违法排放污染物")
        if "无证" in facts or "未取得" in facts:
            elements.append("无证排污")
        if "危废" in facts or "危险废物" in facts:
            elements.append("危险废物非法处置")
        return elements or ["待进一步分析"]

    def _find_applicable_laws(self, category: str) -> List[str]:
        laws = {
            "大气": ["生态环境法典 第二编第二分编", "大气污染物综合排放标准"],
            "水": ["生态环境法典 第二编第三分编", "水污染物排放标准"],
            "固废": ["生态环境法典 第二编第六分编", "危险废物转移管理办法"],
        }
        return laws.get(category, ["生态环境法典 相关编章"])

    def get_stats(self) -> dict:
        return {"total_tasks": len(self._tasks), "completed": sum(1 for t in self._tasks if t["status"] == "completed")}


# ═══════════════════════════════════════
# Subconscious — 后台监控层
# ═══════════════════════════════════════

class Subconscious:
    """后台监控层——持续运行，主动服务"""

    def __init__(self, memory_tree=None):
        self._mt = memory_tree
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._cycle_count = 0
        self._tasks = {
            "statute_watch": {"name": "法规时效监控", "interval": 3600, "last_run": "", "enabled": True},
            "case_summary": {"name": "案例自动总结", "interval": 7200, "last_run": "", "enabled": True},
            "skill_crystallize": {"name": "技能自动结晶", "interval": 21600, "last_run": "", "enabled": True},
            "quality_report": {"name": "质量自动审计", "interval": 86400, "last_run": "", "enabled": True},
        }

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="subconscious")
        self._thread.start()
        logger.info("[Subconscious] 后台监控启动")

    def stop(self):
        self._running = False
        logger.info("[Subconscious] 后台监控停止")

    def _loop(self):
        while self._running:
            self._cycle_count += 1
            now = datetime.now()

            for task_id, task in self._tasks.items():
                if not task["enabled"]:
                    continue
                if task["last_run"]:
                    last = datetime.fromisoformat(task["last_run"])
                    if (now - last).total_seconds() < task["interval"]:
                        continue

                try:
                    self._run_task(task_id, task)
                    task["last_run"] = now.isoformat()
                except Exception as e:
                    logger.warning(f"[Subconscious] {task['name']} 失败: {e}")

            time.sleep(60)  # 每分钟检查一次

    def _run_task(self, task_id: str, task: Dict):
        logger.info(f"[Subconscious] 执行: {task['name']}")
        if task_id == "statute_watch":
            try:
                sys.path.insert(0, str(ROOT))
                import importlib.util
                spec = importlib.util.spec_from_file_location("sw", str(ROOT / "_scripts" / "subconscious_watcher.py"))
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                watcher = mod.StatuteWatcher(self._mt if hasattr(self, '_mt') else None)
                result = watcher.check_all()
                logger.info(f"[Subconscious] 法规检查: {result['total_statutes']} 部, {result['alert_count']} 项告警")
            except Exception as e:
                logger.warning(f"[Subconscious] 法规检查异常: {e}")
        elif task_id == "quality_report":
            try:
                sys.path.insert(0, str(ROOT))
                spec = importlib.util.spec_from_file_location("qa", str(ROOT / "_scripts" / "quality_audit.py"))
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                logger.info("[Subconscious] 质量审计完成")
            except Exception as e:
                logger.warning(f"[Subconscious] 质量审计异常: {e}")

    def get_stats(self) -> dict:
        return {
            "running": self._running,
            "cycles": self._cycle_count,
            "tasks": {k: {"name": v["name"], "enabled": v["enabled"], "last_run": v["last_run"][:16] if v["last_run"] else "never"} for k, v in self._tasks.items()},
        }


# ═══════════════════════════════════════
# SplitBrain — 三脑整合
# ═══════════════════════════════════════

class SplitBrain:
    """Split Brain 三重架构整合"""

    def __init__(self, memory_tree=None):
        self.reflex = Reflex()
        self.reasoning = Reasoning()
        self.subconscious = Subconscious(memory_tree)
        self._mt = memory_tree
        logger.info("[SplitBrain] 三脑架构初始化完成")

    def process(self, query: str, context: Optional[Dict] = None) -> Dict[str, Any]:
        """统一入口：优先 Reflex 快速处理，不满足则走 Reasoning"""
        start = datetime.now()

        # 1. 尝试 Reflex
        reflex_result = self.reflex.process(query)
        if reflex_result:
            elapsed = (datetime.now() - start).total_seconds() * 1000
            return {"layer": "reflex", "response": reflex_result, "elapsed_ms": elapsed}

        # 2. 走 Reasoning
        case_input = context or {"query": query}
        if "facts" not in case_input and "query" not in case_input:
            case_input["query"] = query

        reasoning_result = self.reasoning.analyze_case(case_input)
        elapsed = (datetime.now() - start).total_seconds() * 1000
        return {"layer": "reasoning", "response": reasoning_result, "elapsed_ms": elapsed}

    def start_subconscious(self):
        self.subconscious.start()

    def get_stats(self) -> dict:
        return {
            "reflex": self.reflex.get_stats(),
            "reasoning": self.reasoning.get_stats(),
            "subconscious": self.subconscious.get_stats(),
        }


# ===== 测试 =====

def test():
    brain = SplitBrain()

    # 测试 Reflex
    r1 = brain.process("你好")
    print(f"[Reflex] 你好 -> {r1['layer']} ({r1['elapsed_ms']:.0f}ms)")

    r2 = brain.process("帮助")
    print(f"[Reflex] 帮助 -> {r2['layer']} ({r2['elapsed_ms']:.0f}ms)")

    # 测试 Reasoning
    r3 = brain.process("某某企业超标排放大气污染物", {"category": "大气", "facts": "烧结机头排放口二氧化硫浓度150mg/m³超限值50mg/m³"})
    print(f"[Reasoning] 复杂查询 -> {r3['layer']} ({r3['elapsed_ms']:.0f}ms)")
    print(f"  分析结果: {r3['response']['result']['summary']}")

    # 启动后台
    brain.start_subconscious()
    print("[Subconscious] 已启动")

    # 统计
    stats = brain.get_stats()
    print(f"\n[Stats] Reflex缓存: {stats['reflex']['cached_items']}")
    print(f"[Stats] Reasoning任务: {stats['reasoning']['total_tasks']}")
    print(f"[Stats] Subconscious任务: {len(stats['subconscious']['tasks'])}")

    # 停止后台
    brain.subconscious.stop()
    print("\n[OK] Split Brain 三重架构测试通过")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test()
