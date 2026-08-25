#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
agent_core/suggest.py — 会话后建议提示词（对标 DSH suggest-prompt 插件）
=====================================================================

每个回合结束后为军哥提供 1-3 条可点击的后续提问建议（Web UI 渲染为
快捷气泡，点击即填入输入框）。

默认规则引擎（零 API 成本、确定性）：
- 依据：上一轮用户消息、回复内容、本轮调用的工具、当前执法阶段、错误状态
- 若配置 ECO_SUGGEST_LLM=1，则追加 LLM 生成建议（失败静默降级规则引擎）
"""

from __future__ import annotations

import os
import re

# 执法平台工具 → 追问模板
_TOOL_FOLLOWUPS: dict[str, str] = {
    "sthjzf_water_task_statistics": "查看冷水江市待核实任务的具体线索详情",
    "sthjzf_water_task_list": "把任务台账里待核实的线索整理成核查要点清单",
    "sthjzf_query_cases": "查询案件详情，并检索对应法典条文",
    "sthjzf_query_case_statistics": "把案件来源类型统计整理成月度执法态势报告",
    "wryzxjc_list_alarms": "拉取超标预警数据的历史趋势（分钟/时/日）",
    "wryzxjc_list_devices": "筛查断线设备清单，生成现场核查线索表",
    "wryzxjc_list_pollution_sources": "查询该污染源的实时与历史监测数据",
    "permit_license_list": "把许可证查询结果落盘为核查清单",
    "permit_jgzf_license_execution": "汇总未提交执行报告的企业名单",
    "hunan_case_list": "打包下载相关案卷 PDF 并归档",
    "statute_lookup": "引用条文出处是否准确？帮我逐条核对",
    "statute_search": "继续检索相关司法解释与裁量基准",
    "kb_search": "基于知识库案例，给出类案处理要点",
    "execute_code": "把计算结果整理成报告并落盘",
    "query_air_quality": "对比昨日空气质量，分析变化趋势",
}

_PHASE_FOLLOWUPS: dict[str, str] = {
    "inspection": "切换到文书阶段，起草现场检查笔录",
    "documentation": "对文书做一次案卷评查（程序/证据/法条三查）",
    "review": "把评查问题清单落盘为整改跟踪表",
}

_GENERIC = [
    "把以上结论落盘为 Markdown 报告",
    "对回答中的法条引用逐条核验出处",
    "生成一份可执行的现场核查计划",
]

_ERROR_FOLLOWUPS = [
    "重试一次刚才的问题",
    "检查服务器日志与网络连通性",
]


def build_suggestions(message: str, reply: str, trace: list | None = None,
                      phase: str = "inspection") -> list[str]:
    """规则引擎：生成 1-3 条后续提问建议（确定性、零 API 成本）。"""
    trace = trace or []
    used_tools: list[str] = []
    for ev in trace:
        if ev.get("type") == "tool":
            used_tools.append(str(ev.get("name", "") or ev.get("tool", "") or ""))

    out: list[str] = []
    is_error = reply.startswith("[eco-server]")

    # 1. 错误回复 → 重试建议优先
    if is_error:
        out.extend(_ERROR_FOLLOWUPS[:2])
        return out[:3]

    # 2. 本轮调用过的工具 → 精准追问
    for t in used_tools:
        f = _TOOL_FOLLOWUPS.get(t)
        if f and f not in out:
            out.append(f)
        if len(out) >= 2:
            break

    # 3. 落盘纪律：回复含结论/清单/报告但未落盘 → 建议落盘
    if not is_error and "save_document" not in used_tools and (
        re.search(r"清单|报告|要点|台账|结论|记录", reply[:400])):
        candidate = "把以上内容落盘为 Markdown 报告"
        if candidate not in out:
            out.append(candidate)

    # 4. 阶段推进建议
    phase_f = _PHASE_FOLLOWUPS.get(phase)
    if phase_f and phase_f not in out:
        out.append(phase_f)

    # 5. 兜底通用建议
    for g in _GENERIC:
        if g not in out:
            out.append(g)
        if len(out) >= 3:
            break
    return out[:3]


def _llm_suggestions(message: str, reply: str) -> list[str]:
    """LLM 生成建议（ECO_SUGGEST_LLM=1 时启用；任何失败返回空列表）。"""
    try:
        from agent_core.llm_client import get_default_client

        client = get_default_client()
        if not client.available():
            return []
        prompt = (
            "基于下面这段执法 AI 助手与用户的对话，给出 3 条简洁的中文后续提问建议"
            "（每条不超过 20 字，直接输出建议本身，每行一条，不要编号）：\n\n"
            f"用户：{message[:300]}\n\n助手：{reply[:600]}\n"
        )
        result = client.chat(
            [{"role": "user", "content": prompt}],
            model=os.environ.get("ECO_SUGGEST_MODEL", "deepseek-chat"),
        )
        if result.get("_error"):
            return []
        text = str(result.get("choices", [{}])[0].get("message", {}).get("content", ""))
        lines = [ln.strip(" -•·\t1234567890.、") for ln in text.splitlines()]
        lines = [ln for ln in lines if 2 <= len(ln) <= 40]
        return lines[:3]
    except Exception:  # noqa: BLE001 — 建议属于增值功能，失败静默
        return []


def build_suggestions_hybrid(message: str, reply: str, trace: list | None = None,
                             phase: str = "inspection") -> list[str]:
    """规则 + 可选 LLM 混合：LLM 建议前置，规则兜底补齐到 3 条。"""
    rules = build_suggestions(message, reply, trace, phase)
    if os.environ.get("ECO_SUGGEST_LLM", "").strip().lower() not in ("1", "true", "yes"):
        return rules
    llm = _llm_suggestions(message, reply)
    merged: list[str] = []
    for s in llm + rules:
        if s not in merged:
            merged.append(s)
    return merged[:3]
