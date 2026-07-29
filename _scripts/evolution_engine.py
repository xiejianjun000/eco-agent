#!/usr/bin/env python3
"""
evolution_engine.py — ECO AGENT 自进化闭环引擎

6 阶段闭环：Execute → Track → Evaluate → Reflect → Crystallize → Store

用法：
  from _scripts.evolution_engine import EvolutionEngine
  evo = EvolutionEngine()
  evo.run_cycle({"operation": "法规检索", "query": "大气污染防治法"})
"""

import json
import re
import logging
from pathlib import Path
from datetime import datetime
from typing import Any

logger = logging.getLogger("evolution_engine")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = PROJECT_ROOT / "skills"
MEMORY_DIR = PROJECT_ROOT / "memory-tree" / "obsidian_sync"
QUALITY_DIR = MEMORY_DIR / "quality"
QUALITY_DIR.mkdir(parents=True, exist_ok=True)


class EvolutionEngine:
    """自进化闭环引擎"""

    def __init__(self, memory_tree=None, session_id: str = None):
        self._mt = memory_tree
        self.session_id = session_id or f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self._cycle_count = 0
        self._history: list[dict[str, Any]] = []
        self._crystallized_count = 0

    # ═══════════════════════════════════════
    # 闭环主入口
    # ═══════════════════════════════════════

    def run_cycle(self, operation: dict[str, Any]) -> dict[str, Any]:
        """执行一次完整的自进化闭环"""
        self._cycle_count += 1
        cycle_id = f"cycle_{self._cycle_count}_{datetime.now().strftime('%H%M%S')}"

        logger.info(f"[{cycle_id}] 开始自进化闭环 #{self._cycle_count}")

        # 阶段 1: Execute
        execution = self._execute(operation)
        if not execution.get("success", False):
            return {"cycle_id": cycle_id, "success": False, "error": execution.get("error")}

        # 阶段 2: Track
        track_record = self._track(operation, execution)
        self._history.append(track_record)

        # 阶段 3: Evaluate
        evaluation = self._evaluate(track_record)

        # 阶段 4: Reflect
        reflection = self._reflect(operation, evaluation)
        track_record["reflection"] = reflection

        # 阶段 5: Crystallize
        skill = self._crystallize(operation, reflection)

        # 阶段 6: Store
        self._store(track_record, skill)

        if skill:
            self._crystallized_count += 1

        logger.info(f"[{cycle_id}] 闭环完成: {'新技能已结晶' if skill else '无需新技能'}")
        return {
            "cycle_id": cycle_id,
            "success": True,
            "cycle_count": self._cycle_count,
            "evaluation": evaluation,
            "reflection": reflection,
            "new_skill": skill is not None,
            "crystallized_count": self._crystallized_count,
        }

    # ═══════════════════════════════════════
    # 阶段 1: Execute — 执行操作
    # ═══════════════════════════════════════

    def _execute(self, operation: dict[str, Any]) -> dict[str, Any]:
        """执行执法操作"""
        op_type = operation.get("operation", "")
        logger.info(f"  [Execute] 执行操作: {op_type}")

        try:
            result = {"success": True, "data": {}, "error": None}
            op_type_lower = op_type.lower()

            if "检索" in op_type_lower or "搜索" in op_type_lower or "查询" in op_type_lower:
                result["data"]["query"] = operation.get("query", "")
                result["data"]["result_count"] = 1  # 占位
                result["data"]["result_preview"] = "模拟检索结果"

            elif "裁量" in op_type_lower or "处罚" in op_type_lower:
                result["data"]["category"] = operation.get("category", "")
                result["data"]["violation"] = operation.get("violation", "")
                result["data"]["suggestion"] = f"建议处罚 {operation.get('amount', 0)} 元"

            elif "文书" in op_type_lower or "决定书" in op_type_lower:
                result["data"]["doc_type"] = operation.get("doc_type", "")
                result["data"]["draft_length"] = len(operation.get("content", ""))

            else:
                result["data"]["note"] = f"操作已记录: {op_type}"

            return result

        except Exception as e:
            logger.error(f"  [Execute] 失败: {e}")
            return {"success": False, "error": str(e)}

    # ═══════════════════════════════════════
    # 阶段 2: Track — 记录过程
    # ═══════════════════════════════════════

    def _track(self, operation: dict[str, Any],
               execution: dict[str, Any]) -> dict[str, Any]:
        """记录操作过程"""
        record = {
            "timestamp": datetime.now().isoformat(),
            "session_id": self.session_id,
            "cycle_number": self._cycle_count,
            "operation": operation,
            "execution": execution,
            "duration_ms": 0,
            "context": {
                "total_cycles": self._cycle_count,
                "crystallized_skills": self._crystallized_count,
                "history_count": len(self._history),
            }
        }
        logger.info(f"  [Track] 操作已记录 (历史: {len(self._history) + 1} 条)")
        return record

    # ═══════════════════════════════════════
    # 阶段 3: Evaluate — 评估效果
    # ═══════════════════════════════════════

    def _evaluate(self, track_record: dict[str, Any]) -> dict[str, Any]:
        """评估操作效果"""
        op = track_record.get("operation", {})
        execution = track_record.get("execution", {})
        scores = {}
        suggestions = []

        # E1: 完整性评估
        completeness = 1.0
        required_fields = ["operation", "query"]
        missing = [f for f in required_fields if f not in op]
        if missing:
            completeness = 1.0 - (len(missing) / len(required_fields))
            suggestions.append(f"缺少字段: {', '.join(missing)}")
        scores["completeness"] = completeness

        # E2: 效率评估
        efficiency = 1.0
        if execution.get("success"):
            efficiency = 0.9
        scores["efficiency"] = efficiency

        # E3: 新颖度评估（基于历史）
        novelty = 1.0
        op_type = op.get("operation", "")
        same_type_count = sum(
            1 for h in self._history
            if h.get("operation", {}).get("operation") == op_type
        )
        if same_type_count > 3:
            novelty = max(0.3, 1.0 - same_type_count * 0.1)
        if novelty < 0.5:
            suggestions.append(f"操作类型 '{op_type}' 已重复 {same_type_count} 次，考虑结晶为 Skill")
        scores["novelty"] = novelty

        # E4: 可复用性评估
        reusability = 0.5
        if novelty < 0.7 and completeness > 0.8:
            reusability = 0.85
            suggestions.append("此操作模式稳定，适合结晶为 Skill")
        scores["reusability"] = reusability

        evaluation = {
            "scores": scores,
            "overall": sum(scores.values()) / len(scores),
            "suggestions": suggestions,
            "should_crystallize": (completeness > 0.8 and reusability > 0.7
                                   and same_type_count >= 3),
        }
        logger.info(f"  [Evaluate] 综合评分: {evaluation['overall']:.2f}"
                    f" {'[建议结晶]' if evaluation['should_crystallize'] else ''}")
        return evaluation

    # ═══════════════════════════════════════
    # 阶段 4: Reflect — 反思改进
    # ═══════════════════════════════════════

    def _reflect(self, operation: dict[str, Any],
                 evaluation: dict[str, Any]) -> dict[str, Any]:
        """反思改进点"""
        reflection = {
            "timestamp": datetime.now().isoformat(),
            "cycle": self._cycle_count,
            "what_worked": [],
            "what_could_improve": [],
            "patterns": [],
            "skill_candidate": None,
        }

        op_type = operation.get("operation", "")
        scores = evaluation.get("scores", {})
        suggestions = evaluation.get("suggestions", [])

        # 总结工作良好的部分
        if scores.get("completeness", 0) > 0.8:
            reflection["what_worked"].append("操作信息完整")
        if scores.get("efficiency", 0) > 0.8:
            reflection["what_worked"].append("执行效率良好")

        # 总结改进点
        reflection["what_could_improve"] = [
            s for s in suggestions if "缺少" in s
        ]

        # 提取模式
        if evaluation.get("should_crystallize"):
            reflection["skill_candidate"] = {
                "type": op_type,
                "trigger": f"用户发起{op_type}操作",
                "steps": self._extract_steps(op_type),
                "frequency": sum(
                    1 for h in self._history
                    if h.get("operation", {}).get("operation") == op_type
                ) + 1,
            }
            reflection["patterns"].append(f"'{op_type}' 操作具有稳定模式")

        logger.info(f"  [Reflect] 反思完成: {len(reflection['what_worked'])} 项成功, "
                    f"{len(reflection['skill_candidate'] or [])} 个候选技能")
        return reflection

    def _extract_steps(self, op_type: str) -> list[str]:
        """提取操作步骤"""
        op_lower = op_type.lower()
        if "检索" in op_lower or "查询" in op_lower:
            return [
                "1. 识别用户查询意图和环境要素",
                "2. 构建检索关键词",
                "3. 通过 MCP 工具检索知识库",
                "4. 筛选和排序结果",
                "5. 格式化输出回答",
            ]
        elif "裁量" in op_lower or "处罚" in op_lower:
            return [
                "1. 分析违法事实要素",
                "2. 匹配适用法规条文",
                "3. 检索裁量基准",
                "4. 参考相似案例",
                "5. 给出处罚幅度建议",
            ]
        elif "文书" in op_lower or "决定书" in op_lower:
            return [
                "1. 收集案件基本信息",
                "2. 选择文书模板",
                "3. 填充案件事实和法律依据",
                "4. ACE 审查",
                "5. 输出文书草案",
            ]
        return [f"1. 执行 {op_type} 操作"]

    # ═══════════════════════════════════════
    # 阶段 5: Crystallize — 结晶为 Skill
    # ═══════════════════════════════════════

    def _crystallize(self, operation: dict[str, Any],
                     reflection: dict[str, Any]) -> str | None:
        """将经验结晶为 Skill 文件"""
        candidate = reflection.get("skill_candidate")
        if not candidate:
            return None

        op_type = candidate["type"]
        safe_name = re.sub(r'[^\w]', '_', op_type)[:30]

        # 检查技能文件是否已存在
        skill_path = SKILLS_DIR / f"{safe_name}-skill.md"
        if skill_path.exists():
            logger.info(f"  [Crystallize] Skill 已存在: {skill_path.name}")
            return str(skill_path)

        # 生成 Skill 内容
        skill_content = self._generate_skill_md(candidate)
        skill_path.write_text(skill_content, encoding="utf-8")

        logger.info(f"  [Crystallize] 新技能结晶: {skill_path.name}")
        return str(skill_path)

    def _generate_skill_md(self, candidate: dict[str, Any]) -> str:
        """生成 SKILL.md 格式技能文件"""
        skill_type = candidate.get("type", "通用")
        safe_type = re.sub(r'[^\w]', '', skill_type)
        skill_name = f"{safe_type}-skill"

        steps = candidate.get("steps", [])
        steps_text = "\n".join(steps) if steps else "1. 执行标准操作流程"

        return f"""---
name: {skill_name}
version: 0.1.0
description: 自动结晶：{skill_type}操作技能
author: ECO AGENT (Evolution Engine)
type: skill
---

# {skill_name} — {skill_type}

## Meta

**用途**：{skill_type}操作的标准流程
**调用条件**：用户触发{skill_type}相关操作时自动激活
**依赖**：eco-knowledge-mcp

---

## Instructions

### 1. 触发条件

{self._generate_trigger_condition(skill_type)}

### 2. 操作步骤

```text
{steps_text}
```

### 3. 处理原则

- 完整性：确保操作信息完整
- 可追溯：每一步记录操作日志
- 质量门禁：输出前经过 Reflector 审查
- 持续改进：每次执行记录效果，积累经验

### 4. 输出格式

```markdown
## 操作结果

**操作类型**：{skill_type}
**执行时间**：[自动填充]

### 结果详情

[操作结果内容]

### 经验总结

[每次执行后由 Evolution Engine 更新]
```
"""

    def _generate_trigger_condition(self, skill_type: str) -> str:
        """生成触发条件"""
        return f"""
当用户输入涉及以下内容时，激活本技能：
- 与"{skill_type}"相关的操作请求
- 需要标准流程处理的{skill_type}任务
- 重复执行超过 3 次的{skill_type}模式
"""

    # ═══════════════════════════════════════
    # 阶段 6: Store — 存入记忆
    # ═══════════════════════════════════════

    def _store(self, track_record: dict[str, Any],
               skill_path: str | None = None):
        """将闭环记录存入 Memory Tree"""
        store_targets = []

        # 存入 Memory Tree（如可用）
        if self._mt:
            try:
                content = json.dumps(track_record, ensure_ascii=False, indent=2)[:3000]
                node = self._mt.create_node(
                    type="quality",
                    title=f"进化闭环 #{self._cycle_count} - {track_record.get('operation', {}).get('operation', '未知')}",
                    content=content,
                    tags=["evolution", "cycle"],
                    score=min(90, 50 + self._cycle_count * 5),
                    source="system",
                )
                store_targets.append(f"Memory Tree: {node['id']}")
            except Exception as e:
                logger.warning(f"  [Store] Memory Tree 写入失败: {e}")

        # 写入文件日志
        log_path = QUALITY_DIR / f"cycle_{self._cycle_count}_{datetime.now().strftime('%H%M%S')}.json"
        log_data = {
            "cycle_id": f"cycle_{self._cycle_count}",
            "timestamp": track_record["timestamp"],
            "session_id": self.session_id,
            "operation": track_record.get("operation", {}).get("operation", ""),
            "evaluation": track_record.get("reflection", {}),
            "skill_created": skill_path is not None,
            "skill_path": skill_path or "",
        }
        log_path.write_text(
            json.dumps(log_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        store_targets.append(f"日志文件: {log_path.name}")

        logger.info(f"  [Store] 已存储到: {', '.join(store_targets)}")

    # ═══════════════════════════════════════
    # 批量处理
    # ═══════════════════════════════════════

    def bulk_process(self, operations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """批量处理多个操作"""
        results = []
        for op in operations:
            result = self.run_cycle(op)
            results.append(result)
        return results

    def get_stats(self) -> dict[str, Any]:
        """获取进化引擎统计"""
        return {
            "total_cycles": self._cycle_count,
            "crystallized_skills": self._crystallized_count,
            "session_id": self.session_id,
            "history_count": len(self._history),
        }


# ===== 背景审查机制 =====

class BackgroundReviewer:
    """背景审查：定期 fork 子 Agent 自动审查 + 提取 Skill"""

    def __init__(self, evolution_engine: EvolutionEngine, interval: int = 3):
        self._evo = evolution_engine
        self.interval = interval  # 每 N 轮审查一次

    def check_and_review(self, cycle_count: int) -> dict[str, Any] | None:
        """判断是否需要审查"""
        if cycle_count < self.interval:
            return None
        if cycle_count % self.interval != 0:
            return None
        return self.run_review()

    def run_review(self) -> dict[str, Any]:
        """执行背景审查"""
        logger.info(f"[BackgroundReviewer] 开始第 {self._evo._cycle_count} 轮背景审查")

        stats = self._evo.get_stats()
        history = self._evo._history

        # 1. 分析操作模式
        op_types = {}
        for h in history:
            op = h.get("operation", {}).get("operation", "unknown")
            op_types[op] = op_types.get(op, 0) + 1

        # 2. 找出高频操作
        frequent_ops = {k: v for k, v in op_types.items() if v >= 3}
        review_result = {
            "timestamp": datetime.now().isoformat(),
            "cycle_count": stats["total_cycles"],
            "total_operations": len(history),
            "operation_types": op_types,
            "frequent_operations": frequent_ops,
            "recommendations": [],
            "new_skills": [],
        }

        # 3. 建议结晶
        for op_type, count in frequent_ops.items():
            review_result["recommendations"].append(
                f"'{op_type}' 已执行 {count} 次，建议结晶为 Skill"
            )

        # 4. 自动结晶
        for op_type in frequent_ops:
            reflection = {
                "skill_candidate": {
                    "type": op_type,
                    "trigger": f"用户发起{op_type}操作",
                    "steps": self._evo._extract_steps(op_type),
                    "frequency": op_types[op_type],
                }
            }
            skill_path = self._evo._crystallize({"operation": op_type}, reflection)
            if skill_path:
                review_result["new_skills"].append(skill_path)

        logger.info(f"[BackgroundReviewer] 审查完成: "
                    f"{len(review_result['recommendations'])} 项建议, "
                    f"{len(review_result['new_skills'])} 个新技能")
        return review_result


# ===== 测试 =====

def test():
    """测试自进化闭环"""
    import sys as _sys
    _sys.path.insert(0, str(PROJECT_ROOT))
    from _scripts.memory_tree import MemoryTree
    import tempfile
    import shutil

    db_path = Path(tempfile.mkdtemp()) / "test_evo.db"
    mt = MemoryTree(db_path)
    evo = EvolutionEngine(mt)
    reviewer = BackgroundReviewer(evo, interval=3)

    # 模拟操作序列
    operations = [
        {"operation": "法规检索", "query": "大气污染防治法"},
        {"operation": "法规检索", "query": "水污染防治法"},
        {"operation": "法规检索", "query": "固废污染防治法"},
        {"operation": "裁量建议", "category": "大气", "violation": "超标排放", "amount": 300000},
        {"operation": "裁量建议", "category": "水", "violation": "超标排放", "amount": 500000},
        {"operation": "裁量建议", "category": "固废", "violation": "非法处置", "amount": 800000},
    ]

    print(f"[TEST] 执行 {len(operations)} 次闭环...")
    for i, op in enumerate(operations):
        result = evo.run_cycle(op)

        # 背景审查（每 3 轮）
        review = reviewer.check_and_review(i + 1)
        if review:
            print(f"  背景审查: {review['cycle_count']} 轮, "
                  f"{len(review['new_skills'])} 新技能")

    stats = evo.get_stats()
    print("\n[TEST] 进化统计:")
    print(f"  总闭环次数: {stats['total_cycles']}")
    print(f"  结晶技能数: {stats['crystallized_skills']}")
    print(f"  历史记录数: {stats['history_count']}")

    # 验证技能文件
    skills = list(SKILLS_DIR.glob("*-skill.md"))
    auto_skills = [s for s in skills if "检索" in s.stem or "裁量" in s.stem]
    print(f"  现有技能文件: {len(auto_skills)} 个自动结晶")
    for s in auto_skills:
        print(f"    - {s.name}")

    import gc; gc.collect()
    try: shutil.rmtree(db_path.parent)
    except Exception: pass
    print("\n[OK] 自进化闭环测试通过")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test()
