#!/usr/bin/env python3
"""
role_swarm.py — 三角色执法协作（Phase B1，基于 L2 DAG 思路，不引入外部框架）

三角色：
  巡查 Agent (patrol)    现场检查要点 / 证据意识            -> 复用 prompt_engine "inspection" 阶段
  法规 Agent (law)       法条核验 / 裁量                    -> 复用 prompt_engine "review" 阶段精神（法条适用准确）
  文书 Agent (doc)       检查记录 / 巡查清单生成            -> 复用 prompt_engine "documentation" 阶段

DAG：
  patrol ─┐
          ├─> doc ─> synthesis（总管仲裁合成）
  law ────┘
  patrol 与 law 并行；doc 依赖两者产出；synthesis 汇总三角色产出输出最终结论。

成本控制：
  角色子任务走 cheap tier（ECO_SWARM_ROLE_MODEL，默认当前 provider 模型如 deepseek-chat）
  合成走 strong tier（ECO_SWARM_SYNTH_MODEL，缺省回退当前 provider 模型）
  简单问答不启用：is_complex_task() 复杂度判断，避免浪费。

审计：每个角色产出与最终合成均写入 prompt_engine SM3 审计链（source=swarm:<role>）。
输出标注各角色贡献段：result["contributions"] = {role: text}。
"""

import logging
import os
import re
import threading
import time
import uuid

logger = logging.getLogger("role_swarm")

# ── 角色定义 ──
ROLES = {
    "patrol": {
        "name": "巡查Agent",
        "phase": "inspection",
        "soul": "searcher",  # profiles/agents/searcher_soul.md（缺失回退硬编码 brief）
        "brief": ("你是现场巡查专家。针对任务给出现场检查要点：检查对象/部位、"
                  "取证规范（照片、笔录、监测数据、台账）、违法线索初步判断。证据意识优先。"),
        "max_tokens": 700,
    },
    "law": {
        "name": "法规Agent",
        "phase": "review",
        "soul": "reviewer",  # profiles/agents/reviewer_soul.md
        "brief": ("你是法规核验专家。针对任务核验适用法律法规：给出真实现行有效的法规名称与具体条款号，"
                  "说明违法构成与裁量要点；不确定的法条明确标注不确定，禁止编造。"),
        "max_tokens": 700,
    },
    "doc": {
        "name": "文书Agent",
        "phase": "documentation",
        "soul": "writer",  # profiles/agents/writer_soul.md
        "brief": ("你是执法文书专家。根据巡查要点与法规核验结果，生成检查记录框架与巡查清单："
                  "要素完整（当事人/事实/证据/法律依据/裁量说明），用语规范。"),
        "max_tokens": 900,
    },
}
ROLE_ORDER = ["patrol", "law", "doc"]

SYNTH_BRIEF = (
    "你是执法任务总管。三位专家（巡查/法规/文书）已分别给出产出。"
    "请仲裁合成最终输出：去重、纠偏（以法规核验为准）、补漏，"
    "给出一份可执行的检查清单。引用法条保留具体条款号。"
    "格式硬要求：结论先行、要点式，除条文原文引用外总长不超过 300 字，"
    "能用表格/列表绝不用段落，禁止输出编排头（如'三角色协作/贡献段'）。"
    "禁止在最终输出中出现编排内部词汇——'三方/三角色/三位专家/各角色/"
    "巡查Agent/法规Agent/文书Agent/仲裁'一律不得出现，以单人视角直接陈述结论。"
    "用中文，结构清晰。"
)

# ── 复杂度判断（简单问答不启用协作）──
_COMPLEX_HINTS = [
    "全套", "全面检查", "综合执法", "检查方案", "专项行动", "排查", "一案双查",
    "检查清单", "现场检查并", "立案", "案卷", "联合检查", "帮扶检查",
]
_COMPLEX_RE = re.compile("|".join(map(re.escape, _COMPLEX_HINTS)))


def is_complex_task(text: str) -> bool:
    """判断是否复杂执法任务。简单问答返回 False（不启用三角色协作，避免浪费）"""
    t = (text or "").strip()
    if not t:
        return False
    if _COMPLEX_RE.search(t):
        return True
    # 长指令且含"检查"+"生成/出/并"等复合动词视为复杂
    return bool(len(t) >= 30 and ("检查" in t or "执法" in t)
                and re.search(r"生成|出具|并.{0,6}(记录|清单|文书|报告)", t))


class RoleSwarm:
    """三角色协作总管"""

    def __init__(self, client=None, audit_chain=None,
                 role_model: str = "", synth_model: str = ""):
        if client is None:
            from agent_core.llm_client import get_default_client
            client = get_default_client()
        self.client = client
        if audit_chain is None:
            from agent_core.prompt_engine import get_prompt_engine
            audit_chain = get_prompt_engine().audit
        self.audit = audit_chain
        self.role_model = role_model or os.environ.get("ECO_SWARM_ROLE_MODEL", "")
        self.synth_model = synth_model or os.environ.get("ECO_SWARM_SYNTH_MODEL", "")

    def _role_system_prompt(self, role: str) -> str:
        """prompt_engine 安全层（SOUL 驱动）+ 阶段预设 + 角色 soul（profiles/agents）+ 硬编码 brief 兜底"""
        from agent_core.prompt_engine import PHASE_PRESETS, get_prompt_engine
        from agent_core.soul import load_agent_soul
        cfg = ROLES[role]
        eng = get_prompt_engine()
        parts = [eng.safety_layer(), *PHASE_PRESETS[cfg["phase"]]]
        soul_text = load_agent_soul(cfg.get("soul", "")) if cfg.get("soul") else ""
        if soul_text:
            parts.append(f"【角色人格 {cfg['soul']}_soul】\n{soul_text}")
        parts.append(cfg["brief"])  # 硬编码 brief 始终保留为职责兜底
        return "\n\n".join(parts)

    def _call_role(self, role: str, task: str, context: str, task_id: str) -> str:
        cfg = ROLES[role]
        system = self._role_system_prompt(role)
        prompt = task if not context else f"{task}\n\n【前置产出】\n{context}"
        t0 = time.time()
        if hasattr(self.client, "chat"):
            resp = self.client.chat(
                [{"role": "system", "content": system},
                 {"role": "user", "content": prompt}],
                model=self.role_model,
            )
            text = resp.get("choices", [{}])[0].get("message", {}).get("content", "") or ""
        else:  # 测试 mock client 用 complete
            text = self.client.complete(prompt, system=system, max_tokens=cfg["max_tokens"])
        text = text.strip()
        self.audit.append(source=f"swarm:{role}", task_id=task_id,
                          content=f"{cfg['name']}产出: {text[:700]}",
                          phase=cfg["phase"], accepted=True)
        logger.info(f"[RoleSwarm] {role} done in {time.time()-t0:.1f}s, {len(text)} chars")
        return text

    def run(self, task: str, task_id: str = "", context: str = "", on_stage=None) -> dict:
        """执行三角色 DAG：patrol ∥ law -> doc -> synthesis

        on_stage: 可选回调 on_stage(stage: str, detail: str, elapsed: float)，
        用于 CLI 轨迹模式展示各阶段与耗时。"""
        def _stage(stage, detail="", elapsed=0.0):
            if on_stage is not None:
                try:
                    on_stage(stage, detail, elapsed)
                except Exception:
                    pass

        task_id = task_id or f"swarm-{uuid.uuid4().hex[:8]}"
        t0 = time.time()
        _stage("任务分解", "巡查 Agent ∥ 法规 Agent 并行 → 文书 Agent → 总管合成")
        contributions: dict[str, str] = {}
        errors: dict[str, str] = {}

        # ── 第一层：patrol 与 law 并行 ──
        _role_elapsed: dict[str, float] = {}

        def _work(role):
            _t = time.time()
            try:
                contributions[role] = self._call_role(role, task, context, task_id)
            except Exception as e:  # noqa: BLE001
                errors[role] = str(e)
                contributions[role] = ""
            _role_elapsed[role] = time.time() - _t
            _stage(f"{ROLES[role]['name']} 完成", contributions[role][:120], _role_elapsed[role])

        _stage("巡查 Agent / 法规 Agent 并行执行中")
        threads = [threading.Thread(target=_work, args=(r,), daemon=True)
                   for r in ("patrol", "law")]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=180)

        # ── 法规产出自动法条核验（P2-1：law 角色产出带工具校验，反幻觉）──
        try:
            import json as _json
            import subprocess as _sp
            import sys as _sys
            from pathlib import Path as _Path

            lookup = (_Path(__file__).resolve().parent.parent
                      / "ecoskills" / "eco-codex" / "scripts" / "lookup.py")
            cited = sorted({int(x) for x in
                            re.findall(r"第\s*(\d{1,4})\s*条", contributions.get("law", ""))
                            if x.isdigit() and 1 <= int(x) <= 1242})[:10]
            checks = []
            for n in cited:
                r = _sp.run([_sys.executable, str(lookup), "article", str(n)],
                            capture_output=True, text=True, timeout=15)
                ok = r.stdout.strip().startswith("{")
                head = (_json.loads(r.stdout).get("text", "")[:60]
                        if ok else "")
                checks.append(f"- 第{n}条: {'✓ 存在' if ok else '✗ 查无'}"
                              + (f"（{head}…）" if ok else ""))
            if checks:
                contributions["law"] = (contributions.get("law") or "") + \
                    "\n\n【法条核验】（自动工具校验）\n" + "\n".join(checks)
        except Exception:  # noqa: BLE001 — 核验失败不阻断协作
            pass

        # ── 第二层：doc 依赖 patrol + law ──
        doc_ctx = "\n\n".join(
            f"[{ROLES[r]['name']}]\n{contributions.get(r, '')}" for r in ("patrol", "law")
            if contributions.get(r))
        try:
            _stage("文书 Agent 起草中", "基于巡查 + 法规产出")
            _t_doc = time.time()
            contributions["doc"] = self._call_role("doc", task, doc_ctx, task_id)
            _stage("文书 Agent 完成", contributions["doc"][:120], time.time() - _t_doc)
        except Exception as e:  # noqa: BLE001
            errors["doc"] = str(e)
            contributions["doc"] = ""

        # ── 第三层：总管仲裁合成（strong tier）──
        synth_input = "\n\n".join(
            f"【{ROLES[r]['name']}产出】\n{contributions.get(r, '（无产出）')}"
            for r in ROLE_ORDER)
        if hasattr(self.client, "chat"):
            resp = self.client.chat(
                [{"role": "system", "content": SYNTH_BRIEF},
                 {"role": "user", "content": f"任务：{task}\n\n{synth_input}"}],
                model=self.synth_model,
            )
            synthesis = (resp.get("choices", [{}])[0].get("message", {}).get("content", "") or "").strip()
        else:
            synthesis = self.client.complete(
                f"任务：{task}\n\n{synth_input}", system=SYNTH_BRIEF, max_tokens=1200).strip()
        self.audit.append(source="swarm:synthesis", task_id=task_id,
                          content=f"总管合成: {synthesis[:700]}",
                          phase="synthesis", accepted=True)
        _stage("总管合成完成", synthesis[:120], time.time() - t0)

        return {
            "task_id": task_id,
            "task": task,
            "contributions": contributions,   # 各角色贡献段
            "synthesis": synthesis,           # 总管合成最终输出
            "errors": errors,
            "elapsed_s": round(time.time() - t0, 1),
            "roles": {r: ROLES[r]["name"] for r in ROLE_ORDER},
        }

    def format_result(self, result: dict) -> str:
        """格式化输出：标注各角色贡献段 + 最终合成"""
        lines = [f"═══ 三角色协作（task_id={result['task_id']}，耗时 {result['elapsed_s']}s）═══", ""]
        for r in ROLE_ORDER:
            name = ROLES[r]["name"]
            lines.append(f"─── [{name}] 贡献段 ───")
            lines.append(result["contributions"].get(r) or "（无产出）")
            lines.append("")
        lines.append("─── [总管] 仲裁合成（最终输出）───")
        lines.append(result["synthesis"] or "（合成失败）")
        return "\n".join(lines)


_swarm: RoleSwarm | None = None


def get_role_swarm() -> RoleSwarm:
    global _swarm
    if _swarm is None:
        _swarm = RoleSwarm()
    return _swarm


def _reset_for_test():
    global _swarm
    _swarm = None
