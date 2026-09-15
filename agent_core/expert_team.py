#!/usr/bin/env python3
"""
expert_team.py — 声明式领域专家团框架（DSH 契约化扩展思想的落地）

把写死在 role_swarm.py 的「三角色执法 DAG」抽象为可声明的团队：
  TeamSpec = { id, name, domain, description, roles[], synth_brief, synth_tier,
               complexity_hints[], eval_rubric[] }
  RoleSpec = { key, name, phase, soul, brief, max_tokens, tier, tools[],
               depends_on[], verify_articles=False }

运行器通用化 RoleSwarm 已验证成熟的机制：
  - 拓扑 wave 并行执行（DAG 由 depends_on 推导，不再写死）
  - 成本分级（role tier 走便宜模型，synth tier 走强模型；复用 ECO_SWARM_*_MODEL 环境变量）
  - 审计链（每角色产出 + 总管合成均写 prompt_engine 审计链）
  - 法条自动核验（verify_articles 角色产出带工具校验，反幻觉）
  - 贡献段 + 总管合成的最终输出

已内置团队（见 team_specs/）：
  - law_enforcement（执法，平移 RoleSwarm 三角色）
  - air_source（大气溯源，10 角色拓扑，复用 cnemc 真数据）

新增团队（信访 / EIA 审查等）只需在 team_specs/ 加一个 spec 并注册，
无需改动本运行器或 server/api/chat.py 主循环——这正是 DSH 的「契约化扩展」原则。
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("eco.expert_team")


# ───────────────────────────────────────────────────────────
# 声明式规格（纯数据，可序列化；团队 = 一组角色 + DAG + 评测 rubric）
# ───────────────────────────────────────────────────────────
@dataclass
class RoleSpec:
    key: str
    name: str
    brief: str
    phase: str = ""                       # prompt_engine.PHASE_PRESETS 键；未知则容错跳过
    soul: str = ""                        # profiles/agents/<soul>_soul.md；空则不加人格
    max_tokens: int = 800
    tier: str = "role"                    # "role" 便宜模型 / "synth" 强模型
    tools: list[str] = field(default_factory=list)   # 该角色可调用工具（提示层声明，供前端/审计展示）
    depends_on: list[str] = field(default_factory=list)  # DAG 前驱
    verify_articles: bool = False         # 产出后自动核验所引法条条号（反幻觉）


@dataclass
class TeamSpec:
    id: str
    name: str
    domain: str
    description: str
    roles: list[RoleSpec]
    synth_brief: str
    synth_tier: str = "synth"
    complexity_hints: list[str] = field(default_factory=list)  # 命中任一即视为复杂任务
    eval_rubric: list[str] = field(default_factory=list)       # L4 评测要点（人工/自动核对清单）

    @property
    def role_order(self) -> list[str]:
        return [r.key for r in self.roles]


# ───────────────────────────────────────────────────────────
# DAG：由 depends_on 推导拓扑 wave（同 wave 并行，前驱 wave 先完成）
# ───────────────────────────────────────────────────────────
def compute_waves(roles: list[RoleSpec]) -> list[list[str]]:
    by_key = {r.key: r for r in roles}
    placed: set[str] = set()
    waves: list[list[str]] = []
    remaining = set(by_key)
    while remaining:
        wave = [k for k in remaining
                if all((d not in by_key) or (d in placed)
                       for d in by_key[k].depends_on)]
        if not wave:                      # 环或悬空依赖：兜底整体放一波，避免死循环
            wave = list(remaining)
            logger.warning("[expert_team] 检测到可能的环形/悬空依赖，已兜底合并为单 wave：%s", wave)
        waves.append(wave)
        placed |= set(wave)
        remaining -= set(wave)
    return waves


# ───────────────────────────────────────────────────────────
# 运行器
# ───────────────────────────────────────────────────────────
class ExpertTeam:
    """声明式领域专家团运行器（通用化 RoleSwarm）"""

    def __init__(self, spec: TeamSpec, client=None, audit_chain=None,
                 role_model: str = "", synth_model: str = ""):
        if client is None:
            from agent_core.llm_client import get_default_client
            client = get_default_client()
        self.spec = spec
        self.client = client
        if audit_chain is None:
            from agent_core.prompt_engine import get_prompt_engine
            audit_chain = get_prompt_engine().audit
        self.audit = audit_chain
        self.role_model = role_model or os.environ.get("ECO_SWARM_ROLE_MODEL", "")
        self.synth_model = synth_model or os.environ.get("ECO_SWARM_SYNTH_MODEL", "")

    # ── 系统提示词（安全层 + 阶段预设 + 角色人格 + 职责 brief）──
    def _role_system_prompt(self, role: RoleSpec) -> str:
        from agent_core.prompt_engine import PHASE_PRESETS, get_prompt_engine
        from agent_core.soul import load_agent_soul
        eng = get_prompt_engine()
        parts = [eng.safety_layer()]
        if role.phase and role.phase in PHASE_PRESETS:
            parts.extend(PHASE_PRESETS[role.phase])
        elif role.phase:
            logger.warning("[expert_team] 未知阶段 %s（团队 %s），跳过阶段预设", role.phase, self.spec.id)
        soul_text = load_agent_soul(role.soul) if role.soul else ""
        if soul_text:
            parts.append(f"【角色人格 {role.soul}_soul】\n{soul_text}")
        if role.tools:
            parts.append("【可调工具】" + "、".join(role.tools))
        parts.append(role.brief)          # 职责 brief 始终保留为兜底
        return "\n\n".join(parts)

    # ── 单角色调用 ──
    def _call_role(self, role: RoleSpec, task: str, context: str, task_id: str) -> str:
        system = self._role_system_prompt(role)
        prompt = task if not context else f"{task}\n\n【前置产出】\n{context}"
        t0 = time.time()
        model = self.synth_model if role.tier == "synth" else self.role_model
        if hasattr(self.client, "chat"):
            resp = self.client.chat(
                [{"role": "system", "content": system},
                 {"role": "user", "content": prompt}],
                model=model,
            )
            text = (resp.get("choices", [{}])[0].get("message", {}).get("content", "") or "")
        else:                               # 测试 mock client 走 complete
            text = self.client.complete(prompt, system=system, max_tokens=role.max_tokens)
        text = text.strip()
        self.audit.append(source=f"team:{self.spec.id}:{role.key}", task_id=task_id,
                          content=f"{role.name}产出: {text[:700]}", phase=role.phase or "team",
                          accepted=True)
        logger.info("[expert_team/%s] %s done in %.1fs, %d chars", self.spec.id, role.key, time.time() - t0, len(text))
        return text

    # ── 法条自动核验（反幻觉，复用 eco-codex/scripts/lookup.py）──
    def _verify_articles(self, role: RoleSpec, contribution: str, task_id: str) -> str:
        try:
            import json as _json
            import subprocess as _sp
            import sys as _sys
            from pathlib import Path as _Path

            lookup = (_Path(__file__).resolve().parent.parent
                      / "ecoskills" / "eco-codex" / "scripts" / "lookup.py")
            cited = sorted({int(x) for x in
                            re.findall(r"第\s*(\d{1,4})\s*条", contribution)
                            if x.isdigit() and 1 <= int(x) <= 1242})[:10]
            checks = []
            for n in cited:
                r = _sp.run([_sys.executable, str(lookup), "article", str(n)],
                            capture_output=True, text=True, timeout=15)
                ok = r.stdout.strip().startswith("{")
                head = (_json.loads(r.stdout).get("text", "")[:60] if ok else "")
                checks.append(f"- 第{n}条: {'✓ 存在' if ok else '✗ 查无'}"
                              + (f"（{head}…）" if ok else ""))
            if checks:
                return contribution + "\n\n【法条核验】（自动工具校验）\n" + "\n".join(checks)
        except Exception:                   # 核验失败不阻断协作
            pass
        return contribution

    def run(self, task: str, task_id: str = "", context: str = "", on_stage: Callable | None = None) -> dict:
        """执行团队 DAG：按 compute_waves 逐 wave 并行 -> 总管合成

        on_stage(stage, detail, elapsed) 用于轨迹展示。"""
        def _stage(stage, detail="", elapsed=0.0):
            if on_stage is not None:
                try:
                    on_stage(stage, detail, elapsed)
                except Exception:
                    pass

        task_id = task_id or f"team-{self.spec.id}-{uuid.uuid4().hex[:8]}"
        t0 = time.time()
        spec = self.spec
        order = spec.role_order
        contributions: dict[str, str] = {}
        errors: dict[str, str] = {}
        role_by_key = {r.key: r for r in spec.roles}

        waves = compute_waves(spec.roles)
        _stage("任务分解", f"{spec.name}：{len(waves)} 个 wave，角色 {order}")

        for wi, wave in enumerate(waves):
            _stage(f"wave {wi + 1}/{len(waves)} 并行执行", " / ".join(role_by_key[r].name for r in wave))
            def _work(key):
                _t = time.time()
                r = role_by_key[key]
                ctx = "\n\n".join(
                    f"[{role_by_key[d].name}]\n{contributions.get(d, '')}"
                    for d in r.depends_on if contributions.get(d))
                try:
                    out = self._call_role(r, task, ctx, task_id)
                    if r.verify_articles:
                        out = self._verify_articles(r, out, task_id)
                    contributions[key] = out
                except Exception as e:  # noqa: BLE001
                    errors[key] = str(e)
                    contributions[key] = ""
                _stage(f"{r.name} 完成", contributions[key][:120], time.time() - _t)

            threads = [threading.Thread(target=_work, args=(k,), daemon=True) for k in wave]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=180)

        # ── 总管仲裁合成（synth tier）──
        synth_input = "\n\n".join(
            f"【{role_by_key[r].name}产出】\n{contributions.get(r, '（无产出）')}" for r in order)
        synth_system = spec.synth_brief
        if hasattr(self.client, "chat"):
            resp = self.client.chat(
                [{"role": "system", "content": synth_system},
                 {"role": "user", "content": f"任务：{task}\n\n{synth_input}"}],
                model=self.synth_model,
            )
            synthesis = (resp.get("choices", [{}])[0].get("message", {}).get("content", "") or "").strip()
        else:
            synthesis = self.client.complete(
                f"任务：{task}\n\n{synth_input}", system=synth_system, max_tokens=1400).strip()
        self.audit.append(source=f"team:{spec.id}:synthesis", task_id=task_id,
                          content=f"总管合成: {synthesis[:700]}", phase="synthesis", accepted=True)
        _stage("总管合成完成", synthesis[:120], time.time() - t0)

        return {
            "team_id": spec.id,
            "team_name": spec.name,
            "task_id": task_id,
            "task": task,
            "contributions": contributions,
            "synthesis": synthesis,
            "errors": errors,
            "elapsed_s": round(time.time() - t0, 1),
            "roles": {r.key: r.name for r in spec.roles},
            "waves": waves,
        }

    def format_result(self, result: dict) -> str:
        role_by_key = {r.key: r for r in self.spec.roles}
        lines = [f"═══ {self.spec.name}（team_id={result['team_id']}，耗时 {result['elapsed_s']}s）═══", ""]
        for r in self.spec.role_order:
            name = role_by_key[r].name
            lines.append(f"─── [{name}] 贡献段 ───")
            lines.append(result["contributions"].get(r) or "（无产出）")
            lines.append("")
        lines.append(f"─── [总管] 仲裁合成（最终输出）───")
        lines.append(result["synthesis"] or "（合成失败）")
        return "\n".join(lines)


# ───────────────────────────────────────────────────────────
# 复杂度判定（每团队自带 hints；命中即启用协作，简单问答不浪费）
# ───────────────────────────────────────────────────────────
_DOMAIN_FALLBACK_KW = ["大气", "空气", "污染", "执法", "检查", "环评", "信访", "溯源", "监测"]
_ACTION_FALLBACK_RE = re.compile(r"生成|出具|分析|研判|并.{0,6}(记录|清单|文书|报告|建议|方案)")


def is_complex_task(spec: TeamSpec, text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if any(h in t for h in spec.complexity_hints):
        return True
    # 通用兜底：长指令 + 含领域词 + 复合动作动词
    return bool(len(t) >= 30 and any(k in t for k in _DOMAIN_FALLBACK_KW)
                and _ACTION_FALLBACK_RE.search(t))


# ───────────────────────────────────────────────────────────
# 团队注册表（新增团队只需 import team_specs 即自动注册）
# ───────────────────────────────────────────────────────────
REGISTRY: dict[str, TeamSpec] = {}


def register(spec: TeamSpec) -> None:
    REGISTRY[spec.id] = spec
    logger.info("[expert_team] 注册团队：%s（%s，%d 角色）", spec.id, spec.name, len(spec.roles))


def get_team(team_id: str) -> TeamSpec | None:
    return REGISTRY.get(team_id)


def list_teams() -> list[TeamSpec]:
    return list(REGISTRY.values())


def run_team(team_id: str, task: str, **kw) -> dict:
    spec = get_team(team_id)
    if spec is None:
        raise KeyError(f"未知团队：{team_id}；可用：{list(REGISTRY)}")
    return ExpertTeam(spec, **kw).run(task)


# 注册内置团队（import team_specs 时执行）
def _auto_register() -> None:
    try:
        from agent_core.team_specs import law_enforcement, air_source
        for mod in (law_enforcement, air_source):
            for attr in vars(mod).values():
                if isinstance(attr, TeamSpec):
                    register(attr)
    except Exception as e:  # noqa: BLE001 — 注册失败不应阻断导入
        logger.warning("[expert_team] 团队自动注册失败：%s", e)


_auto_register()
