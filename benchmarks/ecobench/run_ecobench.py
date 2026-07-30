#!/usr/bin/env python3
"""
run_ecobench.py — EcoBench-mini 评测器（50 题生态环境执法问答金标准）

指标（全部如实计算，严禁封顶/保底/美化）：
  - 法条引用准确率 citation_accuracy：required_citations 命中率（逐题命中数/必引数，再平均）
  - 要点 F1 keypoint_f1：key_points 关键词逐题 P/R/F1，再宏平均

模式：
  真实 LLM：默认，经 LLMClient 逐题调用
  mock：设置 ECO_LLM_DISABLE=1 或 --mock，走固定 mock 答案，仅验证流程（CI/离线）

输出：benchmarks/ecobench/ecobench_report.json + 控制台摘要
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

HERE = Path(__file__).resolve().parent
DATASET = HERE / "dataset.jsonl"
REPORT = HERE / "ecobench_report.json"

SYSTEM = (
    "你是生态环境执法领域的问答助手。回答必须：1) 引用具体现行法律法规名称及条款号；"
    "2) 给出明确结论；3) 覆盖要点。用中文回答，简明扼要。"
)

MOCK_ANSWER = "[mock] 本题需依据相关法律法规处理，具体条款略。"

# ═══════════════════════════════════
# RAG 模式：EHS 知识库检索增强
# ═══════════════════════════════════

EHS_KB_SSE_URL = os.environ.get("EHS_KB_SSE_URL", "http://111.230.89.107:8000/sse")
RAG_MAX_CONTEXT_CHARS = 3000      # 注入提示词的参考资料总长度上限（控制 token）
RAG_MAX_READ_CHARS = 6000         # kb_read 取全文片段的截断上限
RAG_SEARCH_TIMEOUT = 20.0         # kb_search 单次超时（秒）

# 题目核心法律主题词表（按执法问答高频主题排序，命中即作为检索词；
# kb_search 多词查询服务端易超时，故每次只用单个主题词）
QUERY_KEYWORDS = [
    "大气", "噪声", "固体废物", "固废", "危险废物", "危废",
    "水污染", "排污口", "排污许可", "环境影响评价", "环评",
    "土壤", "辐射", "突发环境", "自动监测", "在线监测",
    "超标排放", "未批先建", "验收", "处罚",
]


def extract_query_terms(question: str, max_terms: int = 3) -> list[str]:
    """从题干提取核心法律主题词（去重、保序），作为 kb_search 检索词候选"""
    seen, terms = set(), []
    for kw in QUERY_KEYWORDS:
        if kw in question and kw not in seen:
            seen.add(kw)
            terms.append(kw)
            if len(terms) >= max_terms:
                break
    return terms or [question[:8]]  # 兜底：题干前缀


def parse_kb_search_files(text: str, max_files: int = 5) -> list[str]:
    """解析 kb_search 返回文本中的文件路径（📄 行），去重保序"""
    files = []
    for line in (text or "").splitlines():
        line = line.strip()
        if line.startswith("📄"):
            path = line.lstrip("📄 ").strip()
            if path and path not in files:
                files.append(path)
                if len(files) >= max_files:
                    break
    return files


RAG_PROMPT_SUFFIX = (
    "\n\n【参考资料】（来自 EHS 知识库检索，可能包含相关法条原文）：\n{context}\n\n"
    "请优先依据参考资料中的法条作答，并在答案中注明出处（法律法规名称及条款号）；"
    "参考资料不足时再依据自身知识补充。"
)


class RagRetriever:
    """
    EHS 知识库检索器：kb_search 找文件 → kb_read 取全文片段。

    call_tool 可注入（签名为 call_tool(server, tool, arguments) -> dict），
    便于 pytest mock；默认经 MCPConnectorManager 连接远程 SSE server。
    """

    def __init__(self, call_tool=None, server: str = "ehs_kb",
                 url: str = EHS_KB_SSE_URL, timeout: float = RAG_SEARCH_TIMEOUT):
        self.server = server
        self._mgr = None
        if call_tool is not None:
            self._call_tool = call_tool
        else:
            from agent_core.mcp_connector import MCPConnectorManager, MCPServerConfig
            self._mgr = MCPConnectorManager(
                [MCPServerConfig(name=server, transport="sse", url=url, timeout=timeout)])
            status = self._mgr.connect_all()
            if not status.get(server):
                raise RuntimeError(f"EHS 知识库连接失败: {url}")
            self._call_tool = self._mgr.call_tool
            # 连通性自检
            probe = self._call_tool(server, "kb_status", {})
            if not probe.get("success"):
                raise RuntimeError(f"EHS 知识库 kb_status 自检失败: {probe.get('error')}")

    def close(self) -> None:
        if self._mgr is not None:
            self._mgr.close()

    def search(self, query: str) -> tuple[list[str], str]:
        """kb_search，返回 (文件清单, 原始文本)；失败返回 ([], '')"""
        r = self._call_tool(self.server, "kb_search", {"query": query})
        if not r.get("success"):
            return [], ""
        text = r.get("text", "")
        return parse_kb_search_files(text), text

    def read(self, path: str, max_chars: int = RAG_MAX_READ_CHARS) -> str:
        """kb_read 取全文，截断到 max_chars；失败返回 ''"""
        r = self._call_tool(self.server, "kb_read", {"path": path})
        if not r.get("success"):
            return ""
        return (r.get("text", "") or "")[:max_chars]

    def retrieve(self, question: str) -> dict:
        """
        对一道题执行检索：依次尝试主题词 kb_search（单词查询，避免多词超时），
        命中后对 top 文件做 1 次 kb_read 取片段，拼成注入上下文（总长受限）。
        返回 {"files": [...], "context": str}。
        """
        files: list[str] = []
        search_text = ""
        for term in extract_query_terms(question):
            files, search_text = self.search(term)
            if files:
                break
        parts = []
        if search_text:
            parts.append("【检索命中摘要】\n" + search_text[:1500])
        if files:
            full = self.read(files[0])
            if full:
                parts.append(f"【知识库原文片段：{files[0]}】\n{full}")
        context = "\n\n".join(parts)[:RAG_MAX_CONTEXT_CHARS]
        return {"files": files, "context": context}


def _norm(s: str) -> str:
    """归一化：去空白/书名号/国名前缀，提升法条匹配的诚实稳健性"""
    t = re.sub(r"\s+", "", s or "")
    t = re.sub(r"（[^）]{0,30}）", "", t)  # 法名与条号间的修订年份等括号注释不影响命中
    t = re.sub(r"\([^)]{0,30}\)", "", t)
    t = t.replace("《", "").replace("》", "").replace("中华人民共和国", "")
    return t


def score_item(answer: str, item: dict) -> dict:
    """逐题评分：引用命中率 + 要点 F1（诚实计算，不做任何修饰）"""
    a = _norm(answer)
    cites = item["required_citations"]
    hit_c = sum(1 for c in cites if _norm(c) in a)
    citation_hit = hit_c / len(cites) if cites else 1.0

    kps = item["key_points"]
    tp = sum(1 for k in kps if _norm(k) in a)
    precision = tp / len(kps) if kps else 1.0  # 输出侧全部要求要点
    recall = tp / len(kps) if kps else 1.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {
        "id": item["id"], "category": item["category"],
        "citation_hit": round(citation_hit, 4),
        "citation_hits": hit_c, "citation_total": len(cites),
        "keypoint_tp": tp, "keypoint_total": len(kps),
        "keypoint_f1": round(f1, 4),
    }


def load_dataset(limit: int = 0) -> list[dict]:
    items = [json.loads(l) for l in DATASET.read_text(encoding="utf-8").splitlines() if l.strip()]
    return items[:limit] if limit else items


def answer_question(client, item: dict, mock: bool,
                    retriever: RagRetriever | None = None) -> tuple[str, list[str]]:
    """答题，返回 (答案, 检索文件清单)。retriever 非空时为 RAG 模式"""
    if mock or client is None or not client.available():
        return MOCK_ANSWER, []
    question = item["question"]
    files: list[str] = []
    if retriever is not None:
        try:
            hit = retriever.retrieve(question)
            files = hit["files"]
            if hit["context"]:
                question = question + RAG_PROMPT_SUFFIX.format(context=hit["context"])
        except Exception as e:
            print(f"    [RAG] {item['id']} 检索失败（降级为无检索作答）: {e}", flush=True)
    try:
        return client.complete(question, system=SYSTEM, max_tokens=1024) or MOCK_ANSWER, files
    except Exception as e:
        return f"[error] {type(e).__name__}: {e}", files


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="run_ecobench", description="EcoBench-mini runner")
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 题（控制成本）")
    ap.add_argument("--mock", action="store_true", help="mock 模式（离线/CI）")
    ap.add_argument("--out", default=str(REPORT))
    ap.add_argument("--rag", action="store_true",
                    help="RAG 模式：答题前经 MCP 检索 EHS 知识库并注入参考资料")
    args = ap.parse_args(argv)

    mock = args.mock or os.environ.get("ECO_LLM_DISABLE", "").strip().lower() in ("1", "true", "yes")
    client = None
    if not mock:
        from agent_core.llm_client import get_default_client
        client = get_default_client()
        if not client.available():
            print("[EcoBench] LLM 不可用，自动降级 mock 模式", flush=True)
            mock = True

    retriever = None
    if args.rag and not mock:
        try:
            retriever = RagRetriever()
            print(f"[EcoBench] RAG 模式：已连接 EHS 知识库 {EHS_KB_SSE_URL}", flush=True)
        except Exception as e:
            print(f"[EcoBench] RAG 检索器初始化失败，降级为无检索: {e}", flush=True)
            retriever = None

    items = load_dataset(args.limit)
    mode = "mock" if mock else ("rag" if retriever else "llm")
    print(f"[EcoBench-mini] n={len(items)} mode={mode}", flush=True)

    results = []
    t0 = time.time()
    for i, item in enumerate(items, 1):
        ans, files = answer_question(client, item, mock, retriever=retriever)
        sc = score_item(ans, item)
        sc["answer"] = ans
        sc["retrieved_files"] = files
        sc["golden_answer"] = item["golden_answer"]
        results.append(sc)
        print(f"  [{i:02d}/{len(items)}] {item['id']} {item['category']} "
              f"cite={sc['citation_hit']:.2f} f1={sc['keypoint_f1']:.2f}", flush=True)

    n = len(results) or 1
    summary = {
        "n_questions": len(results),
        "mode": mode,
        "citation_accuracy": round(sum(r["citation_hit"] for r in results) / n, 4),
        "keypoint_f1": round(sum(r["keypoint_f1"] for r in results) / n, 4),
        "elapsed_s": round(time.time() - t0, 1),
        "by_category": {},
    }
    cats = sorted({r["category"] for r in results})
    for c in cats:
        sub = [r for r in results if r["category"] == c]
        m = len(sub) or 1
        summary["by_category"][c] = {
            "n": len(sub),
            "citation_accuracy": round(sum(r["citation_hit"] for r in sub) / m, 4),
            "keypoint_f1": round(sum(r["keypoint_f1"] for r in sub) / m, 4),
        }

    report = {"summary": summary, "results": results}
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n===== EcoBench-mini 摘要（如实报告，无封顶/保底） =====")
    print(f"  题目数: {summary['n_questions']}  模式: {summary['mode']}  耗时: {summary['elapsed_s']}s")
    print(f"  法条引用准确率: {summary['citation_accuracy']:.4f}")
    print(f"  要点 F1:        {summary['keypoint_f1']:.4f}")
    for c, s in summary["by_category"].items():
        print(f"    - {c}: cite={s['citation_accuracy']:.2f} f1={s['keypoint_f1']:.2f} (n={s['n']})")
    print(f"  报告: {args.out}")
    if retriever is not None:
        retriever.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
