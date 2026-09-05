#!/usr/bin/env python3
"""
demo_mcp_e2e.py — eco-agent MCP 端到端 demo

场景：执法人员提问 "娄底今天空气怎么样？砖厂巡查要注意什么？"

调用链：
  1. eco-agent L1 用 Kimi（kimi-k2.5）思考，决定调用哪些 MCP 工具
     （LLM 不可用时降级为固定流程顺序调用）
  2. govmcp（stdio，本地子进程）query_air_quality("娄底")
     → 中国环境监测总站 CNEMC 实时 6 参数
  3. EHS 知识库（SSE，远程已部署服务）kb_list / kb_search
     → 砖瓦行业标准 + 现场检查执法要点真实命中
  4. Kimi 综合两路数据生成执法建议（LLM 不可用降级模板输出）
  5. 全程打印调用链（哪步调哪个 MCP 的哪个工具、耗时、返回摘要）

运行：
    python scripts/demo_mcp_e2e.py
环境变量（均有默认值）：
    EHS_KB_SSE_URL   默认 http://111.230.89.107:8000/sse/
    GOVMCP_STDIO_CMD 默认 [python, /tmp/govmcp/scripts/run_mcp_stdio.py]（JSON）
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent_core.llm_client import get_default_client  # noqa: E402
from agent_core.mcp_connector import MCPConnectorManager, MCPServerConfig  # noqa: E402

QUESTION = "娄底今天空气怎么样？砖厂巡查要注意什么？"

# 多词查询会触发 KB 服务端检索超时（服务端已知问题），demo 用单词查询
KB_QUERIES = ["砖瓦工业", "现场检查"]


def _govmcp_cmd() -> list[str]:
    raw = os.environ.get("GOVMCP_STDIO_CMD", "").strip()
    if raw:
        return json.loads(raw)
    return [sys.executable, "/tmp/govmcp/scripts/run_mcp_stdio.py"]


def build_manager() -> MCPConnectorManager:
    configs = [
        MCPServerConfig(
            name="ehs_kb",
            transport="sse",
            url=os.environ.get("EHS_KB_SSE_URL", "http://111.230.89.107:8000/sse/"),
        ),
        MCPServerConfig(
            name="govmcp",
            transport="stdio",
            command=_govmcp_cmd(),
        ),
    ]
    return MCPConnectorManager(configs)


class CallChain:
    """调用链记录器"""

    def __init__(self):
        self.steps: list[dict] = []

    def log(self, step: str, server: str, tool: str, result: dict) -> None:
        entry = {
            "step": step,
            "server": server,
            "tool": tool,
            "elapsed_ms": result.get("elapsed_ms", "-"),
            "success": result.get("success", False),
        }
        self.steps.append(entry)
        mark = "✓" if entry["success"] else "✗"
        print(f"  [{step}] {mark} MCP:{server} → {tool} ({entry['elapsed_ms']}ms)")
        text = result.get("text") or result.get("error", "")
        summary = " ".join(str(text).split())[:160]
        print(f"       摘要: {summary}")

    def print_summary(self) -> None:
        print("\n══ 调用链汇总 ══")
        total = 0
        for i, s in enumerate(self.steps, 1):
            ms = s["elapsed_ms"] if isinstance(s["elapsed_ms"], int) else 0
            total += ms
            print(f"  {i}. [{s['step']}] {s['server']}.{s['tool']} — {'成功' if s['success'] else '失败'} {s['elapsed_ms']}ms")
        print(f"  MCP 调用总耗时: {total}ms")


def llm_plan(available_tools: list[dict]) -> list[dict] | None:
    """L1 思考：让 Kimi 决定工具调用计划，失败返回 None（降级固定流程）"""
    llm = get_default_client()
    if not llm.available():
        print("  [L1] LLM 不可用，降级为固定流程顺序调用")
        return None
    tools_desc = "\n".join(f"- {t['server']}.{t['name']}: {t['description']}" for t in available_tools)
    prompt = (
        f"你是生态环境执法智能体的规划模块。用户问题：「{QUESTION}」\n"
        f"可用 MCP 工具：\n{tools_desc}\n"
        "请输出一个 JSON 数组表示调用计划，每个元素形如 "
        '{"server":"...","tool":"...","arguments":{...}}。'
        "必须包含 govmcp.query_air_quality（region=娄底）和 ehs_kb.kb_search"
        "（query 用单个关键词，如 砖瓦工业 或 现场检查，加 limit=5）。"
        "只输出 JSON，不要其他内容。"
    )
    text = llm.chat([{"role": "user", "content": prompt}], max_tokens=1024)
    if not text:
        print("  [L1] LLM 思考失败，降级为固定流程顺序调用")
        return None
    try:
        start = text.index("[")
        plan = json.loads(text[start : text.rindex("]") + 1])
        assert isinstance(plan, list) and plan
        print(f"  [L1] Kimi 规划 {len(plan)} 步: " + ", ".join(f"{p.get('server')}.{p.get('tool')}" for p in plan))
        return plan
    except Exception as e:
        print(f"  [L1] LLM 计划解析失败({e})，降级为固定流程顺序调用")
        return None


def fixed_plan() -> list[dict]:
    return [
        {"server": "govmcp", "tool": "query_air_quality", "arguments": {"region": "娄底"}},
        {"server": "ehs_kb", "tool": "kb_search", "arguments": {"query": "砖瓦工业", "limit": 5}},
        {"server": "ehs_kb", "tool": "kb_search", "arguments": {"query": "现场检查", "limit": 5}},
    ]


def synthesize(question: str, air: str, kb_hits: list[str]) -> str:
    """综合生成执法建议：优先 Kimi，降级模板"""
    kb_joined = "\n---\n".join(kb_hits)
    llm = get_default_client()
    if llm.available():
        prompt = (
            "你是生态环境执法助手。基于以下实时监测数据与知识库检索结果，"
            f"回答执法人员的问题：「{question}」\n\n"
            f"【CNEMC 实时空气质量】\n{air}\n\n"
            f"【EHS 知识库命中】\n{kb_joined}\n\n"
            "要求：1) 概述娄底当前空气质量（AQI/级别/首要污染物/发布时间）；"
            "2) 结合砖瓦工业相关标准与执法实务，给出砖厂现场巡查要点（3-6 条，具体可操作）；"
            "3) 标注数据来源。用中文回答。"
        )
        text = llm.chat([{"role": "user", "content": prompt}], max_tokens=1500)
        if text:
            return text
        print("  [综合] LLM 生成失败，使用降级模板")
    else:
        print("  [综合] LLM 不可用，使用降级模板")
    return (
        f"【问题】{question}\n\n"
        f"【空气质量（CNEMC 实时）】\n{air}\n\n"
        f"【知识库参考】\n{kb_joined[:800]}\n\n"
        "【巡查要点（规则模式）】\n"
        "1. 对照 GB 29620-2013《砖瓦工业大气污染物排放标准》核查窑炉废气排放浓度；\n"
        "2. 依据 HJ 1103-2020 核查排污许可证载明事项与实际生产工况一致性；\n"
        "3. 关注启停窑时段超标豁免认定（窑启动4h内、停窑2h内）；\n"
        "4. 按现场检查规范制作检查笔录，固定书证/物证/电子数据。"
    )


def main() -> int:
    print("══ eco-agent MCP 端到端 demo ══")
    print(f"问题: {QUESTION}\n")

    mgr = build_manager()
    chain = CallChain()
    try:
        # ── 步骤 0：连接两个 MCP server ──
        print("【步骤 0】连接 MCP servers（失败自动降级跳过）")
        t0 = time.time()
        status = mgr.connect_all()
        for name, ok in status.items():
            tools = [t["name"] for t in mgr.list_tools(name)]
            print(f"  {'✓' if ok else '✗'} {name}: {'已连接，工具: ' + ', '.join(tools) if ok else '连接失败（降级）'}")
        print(f"  连接耗时: {int((time.time() - t0) * 1000)}ms\n")
        if not any(status.values()):
            print("所有 MCP server 均不可用，demo 终止（Agent 仍可跑规则模式）")
            return 1

        # ── 步骤 1：L1 Kimi 思考，决定工具调用计划 ──
        print("【步骤 1】L1 思考（Kimi kimi-k2.5）")
        plan = llm_plan(mgr.all_tools()) or fixed_plan()
        print()

        # ── 步骤 2/3：执行计划 ──
        print("【步骤 2/3】执行 MCP 工具调用")
        air_text = ""
        kb_hits: list[str] = []
        executed = set()
        for p in plan:
            server, tool = p.get("server", ""), p.get("tool", "")
            args = p.get("arguments", {}) or {}
            if not mgr.available(server):
                print(f"  [跳过] {server} 不可用")
                continue
            # kb_search 多词查询服务端会超时，兜底为单词查询
            if tool in ("kb_search", "kb_semantic_search") and " " in str(args.get("query", "")).strip():
                args["query"] = str(args["query"]).split()[0]
            r = mgr.call_tool(server, tool, args)
            chain.log("数据获取", server, tool, r)
            if r.get("success"):
                executed.add((server, tool))
                if server == "govmcp" and tool == "query_air_quality":
                    air_text = r["text"]
                elif server == "ehs_kb" and tool.startswith("kb_"):
                    kb_hits.append(r["text"])
                    executed.add((server, tool, str(args.get("query", ""))))

        # 兜底：计划里缺的关键调用按固定流程补齐
        for p in fixed_plan():
            key = (p["server"], p["tool"])
            if p["tool"].startswith("kb_"):
                # 同一关键词已搜过则跳过；不同关键词补齐
                key = (p["server"], p["tool"], str(p["arguments"].get("query", "")))
            if key in executed or not mgr.available(p["server"]):
                continue
            r = mgr.call_tool(p["server"], p["tool"], p["arguments"])
            chain.log("兜底补调", p["server"], p["tool"], r)
            if r.get("success"):
                executed.add(key)
                if p["tool"] == "query_air_quality":
                    air_text = r["text"]
                else:
                    kb_hits.append(r["text"])
        print()

        # ── 步骤 4：综合生成执法建议 ──
        print("【步骤 4】综合生成执法建议")
        answer = synthesize(QUESTION, air_text or "（空气质量数据不可用）", kb_hits)
        print("\n══ 执法建议输出 ══")
        print(answer)

        chain.print_summary()
        return 0 if air_text or kb_hits else 1
    finally:
        mgr.close()


if __name__ == "__main__":
    sys.exit(main())
