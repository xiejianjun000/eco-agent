#!/usr/bin/env python3
"""
openclaw_features.py — ECO AGENT OpenClaw 对标补全

三项能力：
  1. Plan-as-Tool     — 执法流程注册为 LLM 可调用工具
  2. Per-Agent MCP    — agents 字段过滤 MCP Server 可见性
  3. Progressive Skill — 三级加载 (meta→instructions→resources)

用法：
  from _scripts.openclaw_features import PlanRegistry, MCPGate, SkillLoader
"""

import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger("openclaw")

ROOT = Path(__file__).resolve().parent.parent


# ═══════════════════════════════════════
# 1. Plan-as-Tool
# ═══════════════════════════════════════


class PlanRegistry:
    """执法流程注册表——将多步执法流程注册为 LLM 可调用工具"""

    def __init__(self):
        self._plans: dict[str, dict] = {}
        self._load_defaults()

    def _load_defaults(self):
        self.register(
            "普通处罚流程",
            {
                "description": "一般行政处罚的完整流程（立案→调查→告知→决定→送达）",
                "steps": ["案源登记", "立案审批", "调查取证", "告知听证", "法制审核", "处罚决定", "送达执行", "结案归档"],
                "estimated_time": "15-30 工作日",
                "risk_level": "medium",
            },
        )
        self.register(
            "简易处罚流程",
            {
                "description": "对公民200元以下/法人3000元以下罚款的简易程序",
                "steps": ["现场执法", "告知", "当场处罚", "送达", "结案"],
                "estimated_time": "当场完成",
                "risk_level": "low",
            },
        )
        self.register(
            "按日计罚流程",
            {
                "description": "对拒不改正的违法行为按日连续处罚",
                "steps": ["复查确认未改正", "核算计罚天数", "制作按日计罚决定", "送达", "结案"],
                "estimated_time": "5-10 工作日",
                "risk_level": "high",
            },
        )
        self.register(
            "移送公安流程",
            {
                "description": "涉嫌环境犯罪案件移送公安机关",
                "steps": ["案件审查", "负责人审批", "制作移送书", "移送公安", "跟踪反馈"],
                "estimated_time": "3-7 工作日",
                "risk_level": "high",
            },
        )

    def register(self, name: str, plan: dict) -> bool:
        self._plans[name] = plan
        return True

    def get(self, name: str) -> dict | None:
        return self._plans.get(name)

    def suggest(self, query: str) -> list[dict]:
        """根据用户输入推荐合适的流程"""
        results = []
        q = query.lower()
        for name, plan in self._plans.items():
            score = 0
            if "简易" in q and "简易" in name:
                score += 3
            if "普通" in q and "普通" in name:
                score += 3
            if "公安" in q and "移送" in name:
                score += 3
            if "按日" in q and "按日" in name:
                score += 3
            if "处罚" in q and "处罚" in name:
                score += 1
            if "罚款" in q and ("简易" in name or "普通" in name):
                score += 1
            if score > 0:
                results.append({"name": name, "score": score, "plan": plan})
        results.sort(key=lambda x: -x["score"])
        return [
            {
                "name": r["name"],
                "description": r["plan"]["description"],
                "steps": r["plan"]["steps"],
                "estimated_time": r["plan"]["estimated_time"],
                "risk_level": r["plan"]["risk_level"],
            }
            for r in results
        ]

    def to_tool_schema(self) -> list[dict]:
        """输出 OpenAI Function Calling 格式"""
        return [
            {
                "type": "function",
                "function": {
                    "name": "suggest_plan",
                    "description": "根据执法场景推荐合适的执法流程",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "执法场景描述，如'某企业超标排污'"},
                        },
                        "required": ["query"],
                    },
                },
            }
        ]

    def list_plans(self) -> list[str]:
        return list(self._plans.keys())


# ═══════════════════════════════════════
# 2. Per-Agent MCP — 工具可见性管控
# ═══════════════════════════════════════


class MCPGate:
    """Per-Agent MCP 权限门——控制每个 Agent 能看到哪些 MCP 工具"""

    # 每个 Agent 可见的 MCP 工具白名单
    AGENT_MCP_MAP = {
        "orchestrator": [
            "eco_search",
            "eco_retrieve",
            "eco_statute_query",
            "eco_graph_query",
            "eco_list_statutes",
            "list_tools",
        ],
        "searcher": ["eco_search", "eco_retrieve", "eco_statute_query", "eco_list_statutes"],
        "reviewer": ["eco_retrieve", "eco_statute_query"],
        "writer": ["eco_retrieve"],
        "memory": ["eco_search", "eco_graph_query"],
        "security": ["eco_search"],
        "planner": ["eco_search", "eco_retrieve"],
        "watcher": ["eco_search", "eco_retrieve"],
        "indexer": ["eco_graph_query", "eco_list_statutes"],
    }

    # 每个 MCP 工具的风险等级
    TOOL_RISK = {
        "eco_search": "read",
        "eco_retrieve": "read",
        "eco_statute_query": "read",
        "eco_graph_query": "read",
        "eco_list_statutes": "read",
        "list_tools": "read",
        "eco_execute": "exec",
        "eco_write": "write",
        "eco_delete": "high_risk",
    }

    @classmethod
    def visible_tools(cls, agent_name: str) -> list[str]:
        """返回 Agent 可见的工具列表"""
        return cls.AGENT_MCP_MAP.get(agent_name, ["eco_search", "eco_retrieve"])

    @classmethod
    def check_access(cls, agent_name: str, tool_name: str) -> dict:
        """检查 Agent 是否有权限调用该工具"""
        allowed = tool_name in cls.visible_tools(agent_name)
        risk = cls.TOOL_RISK.get(tool_name, "read")
        if not allowed:
            return {"allowed": False, "reason": f"Agent '{agent_name}' 无权调用 '{tool_name}'", "risk": risk}
        if risk == "high_risk" and agent_name != "orchestrator":
            return {"allowed": False, "reason": "高危工具仅 Orchestrator 可调用", "risk": risk}
        return {"allowed": True, "risk": risk}

    @classmethod
    def get_gate_config(cls) -> dict:
        return {
            "agents": {k: {"visible_tools": v} for k, v in cls.AGENT_MCP_MAP.items()},
            "tool_risks": cls.TOOL_RISK,
        }


# ═══════════════════════════════════════
# 3. Progressive Skill — 三级加载
# ═══════════════════════════════════════


class SkillLoader:
    """渐进式 Skill 加载——三级加载：meta → instructions → resources"""

    def __init__(self):
        self._skills_dir = ROOT / "skills"
        self._agent_profiles_dir = ROOT / "profiles" / "agents"
        self._cache: dict[str, dict] = {}
        self._load_all()

    def _load_all(self):
        """扫描 skills 目录加载所有技能"""
        for f in sorted(self._skills_dir.glob("*.md")):
            self._load_skill_file(f)
        for f in sorted(self._agent_profiles_dir.glob("*_soul.md")):
            self._load_skill_file(f, is_agent=True)

    def _load_skill_file(self, path: Path, is_agent: bool = False):
        content = path.read_text("utf-8", errors="replace")
        name = path.stem

        # 三级抽取
        meta = self._extract_meta(content)
        instructions = self._extract_instructions(content)
        resources = self._extract_resources(content)

        self._cache[name] = {
            "name": name,
            "source": str(path.relative_to(ROOT)),
            "meta": meta,
            "instructions": instructions,
            "resources": resources,
            "is_agent": is_agent,
            "char_count": len(content),
        }

    def _extract_meta(self, content: str) -> dict:
        """提取 meta 层——YAML frontmatter"""
        meta = {}
        if content.startswith("---"):
            end = content.find("---", 3)
            if end != -1:
                for line in content[3:end].strip().split("\n"):
                    if ":" in line:
                        k, _, v = line.partition(":")
                        meta[k.strip()] = v.strip().strip("\"'")
        return meta

    def _extract_instructions(self, content: str) -> str:
        """提取 instructions 层——核心操作指令"""
        # 找 ### Instructions 或 ## Instructions 段落
        patterns = [r"#+\s*Instructions\s*(.*?)(?=##|\Z)", r"#+\s*操作步骤\s*(.*?)(?=##|\Z)"]
        for p in patterns:
            m = re.search(p, content, re.DOTALL)
            if m:
                return m.group(1).strip()[:2000]
        return content[:1000] if not content.startswith("---") else ""

    def _extract_resources(self, content: str) -> list[str]:
        """提取 resources 层——引用的资源文件"""
        resources = []
        for link in re.findall(r"\[\[([^\]]+)\]\]", content):
            resources.append(link)
        for link in re.findall(r"\((raw/|[._]scripts/|[._]skills/[^)]+)\)", content):
            resources.append(link)
        return resources

    def get_level(self, name: str, level: str = "meta") -> Any:
        """按层级获取技能内容"""
        skill = self._cache.get(name)
        if not skill:
            return None
        if level == "meta":
            return skill["meta"]
        elif level == "instructions":
            return skill["instructions"]
        elif level == "resources":
            return skill["resources"]
        return skill

    def search_by_meta(self, key: str, value: str) -> list[dict]:
        """按 meta 字段搜索技能"""
        results = []
        for name, skill in self._cache.items():
            if skill["meta"].get(key) == value:
                results.append({"name": name, "meta": skill["meta"]})
        return results

    def list_by_level(self, level: str = "meta") -> list[dict]:
        """列出指定层级可用的内容"""
        results = []
        for name, skill in self._cache.items():
            item = {"name": name, "source": skill["source"]}
            if level == "meta":
                item["meta"] = skill["meta"]
            elif level == "instructions":
                item["char_count"] = len(skill["instructions"])
            elif level == "resources":
                item["resource_count"] = len(skill["resources"])
            results.append(item)
        return results

    def get_stats(self) -> dict:
        return {
            "total_skills": len(self._cache),
            "agents": sum(1 for s in self._cache.values() if s["is_agent"]),
            "avg_instructions_chars": sum(len(s["instructions"]) for s in self._cache.values()) // max(len(self._cache), 1),
        }


# ═══════════════════════════════════════
# 统一接口
# ═══════════════════════════════════════

plan_registry = PlanRegistry()
mcp_gate = MCPGate()
skill_loader = SkillLoader()


# ===== 测试 =====


def test():
    print("[TEST] OpenClaw 三项能力验证")
    print(f"  {'=' * 40}")

    # 1. Plan-as-Tool
    plans = plan_registry.list_plans()
    print(f"\n[PlanRegistry] 注册流程: {plans}")
    suggestions = plan_registry.suggest("某企业超标排污")
    print(f"  场景匹配: {[s['name'] for s in suggestions]}")
    schema = plan_registry.to_tool_schema()
    print(f"  Tool Schema: {len(schema)} 个")

    # 2. Per-Agent MCP
    print("\n[MCPGate] 可见性管控:")
    for agent in ["searcher", "writer", "planner"]:
        tools = mcp_gate.visible_tools(agent)
        print(f"  {agent}: {tools}")
    check = mcp_gate.check_access("writer", "eco_delete")
    print(f"  writer 调用 eco_delete: {'放行' if check['allowed'] else '拒绝'} ({check['reason']})")

    # 3. Progressive Skill
    print("\n[SkillLoader] 三级加载:")
    print(f"  总技能数: {skill_loader.get_stats()['total_skills']}")
    enforcement = skill_loader.get_level("enforcement-qa-skill", "meta")
    print(f"  enforcement-qa-skill meta: {enforcement}")
    skills_with_desc = skill_loader.search_by_meta("name", "query-skill")
    print(f"  按name查询query-skill: {'找到' if skills_with_desc else '未找到'}")

    print(f"\n{'=' * 40}")
    print("[OK] OpenClaw 三项全部完成")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test()
