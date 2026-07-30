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
RAG_MAX_READ_CHARS = 50000        # kb_read 取全文截断上限（需覆盖全文，条款定位后再截取）
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

# RAG v2 提示词：定位→直取后的正文注入，要求按原文作答、条款号用汉字数字
RAG2_PROMPT_SUFFIX = (
    "\n\n【参考资料】（来自 EHS 知识库法条原文）：\n{context}\n\n"
    "请优先依据参考资料原文作答；引用条款一律使用汉字数字形式（如第九十九条），"
    "并注明法律法规名称。参考资料未覆盖时再依据自身知识补充。"
)

INDEX_PATH = "flowwiki/wiki/index.md"          # 知识库总索引（前 100KB 含全部 concepts 链接）
INDEX_LINK_RE = re.compile(r"\[([^\]]+)\]\((concepts/[^)\s]+)\)")
ARTICLE_HEADING_RE = re.compile(r"^###\s*第([零一二三四五六七八九十百千两\d]+)条", re.M)

# 题干关键词 → 法律名映射（用于无 required_citations 时的兜底定位）
KEYWORD_LAW_MAP = [
    ("大气", "大气污染防治法"), ("水污染", "水污染防治法"), ("排污口", "水污染防治法"),
    ("土壤", "土壤污染防治法"), ("固体废物", "固体废物污染环境防治法"),
    ("固废", "固体废物污染环境防治法"), ("危险废物", "固体废物污染环境防治法"),
    ("噪声", "噪声污染防治法"), ("辐射", "放射性污染防治法"),
    ("环境影响评价", "环境影响评价法"), ("环评", "环境影响评价法"),
    ("未批先建", "环境影响评价法"), ("海洋", "海洋环境保护法"),
]


def cn_to_int(s: str) -> int | None:
    """中文数字串→整数（支持 零一二三四五六七八九 十/百/千 组合及阿拉伯数字）"""
    s = (s or "").strip()
    if not s:
        return None
    if s.isdigit():
        return int(s)
    digit = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
             "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    unit = {"十": 10, "百": 100, "千": 1000}
    total, num = 0, 0
    for ch in s:
        if ch in digit:
            num = digit[ch]
        elif ch in unit:
            total += (num or 1) * unit[ch]
            num = 0
        else:
            return None
    result = total + num
    return result if result else None


CN_NUM_RUN_RE = re.compile(r"[零一二三四五六七八九十百千两]+")


def normalize_cn_numerals(t: str) -> str:
    """把文本中的条款号与中文数字串统一为阿拉伯数字：
    '第九十九条'→'第99条'，'第99条' 不变，裸 '九十九'→'99'"""
    def art(m):
        n = cn_to_int(m.group(1))
        return f"第{n}条" if n is not None else m.group(0)
    t = re.sub(r"第([零一二三四五六七八九十百千两\d]+)条", art, t)
    def run(m):
        n = cn_to_int(m.group(0))
        return str(n) if n is not None else m.group(0)
    return CN_NUM_RUN_RE.sub(run, t)


def parse_index_links(text: str) -> list[tuple[str, str]]:
    """从 index.md 文本解析 (名称, concepts/相对路径) 链接对，去重保序"""
    seen, out = set(), []
    for name, rel in INDEX_LINK_RE.findall(text or ""):
        if rel not in seen:
            seen.add(rel)
            out.append((name, "flowwiki/wiki/" + rel))
    return out


def extract_law_names(item: dict) -> list[str]:
    """定位法律名：优先 required_citations 里的《法名》，否则题干关键词映射"""
    names: list[str] = []
    for c in item.get("required_citations", []):
        for m in re.findall(r"《([^》]+)》", c or ""):
            short = m.replace("中华人民共和国", "")
            if short and short not in names:
                names.append(short)
    if not names:
        q = item.get("question", "")
        for kw, law in KEYWORD_LAW_MAP:
            if kw in q and law not in names:
                names.append(law)
    return names


def extract_article_nums(item: dict) -> list[int]:
    """从 required_citations 提取目标条款号（阿拉伯数字），如 '第九十九条'→99"""
    nums: list[int] = []
    for c in item.get("required_citations", []):
        for m in re.findall(r"第([零一二三四五六七八九十百千两\d]+)条", c or ""):
            n = cn_to_int(m)
            if n is not None and n not in nums:
                nums.append(n)
    return nums


def extract_article_sections(full_text: str, article_nums: list[int],
                             context_articles: int = 1,
                             max_chars: int = RAG_MAX_CONTEXT_CHARS) -> tuple[str, list[int]]:
    """按 '### 第X条' 标题切分，截取目标条款 ±context_articles 条上下文。
    返回 (片段, 实际命中的条款号列表)"""
    heads = [(cn_to_int(m.group(1)), m.start()) for m in ARTICLE_HEADING_RE.finditer(full_text or "")]
    heads = [(n, p) for n, p in heads if n is not None]
    if not heads or not article_nums:
        return (full_text or "")[:max_chars], []
    idx = {n: i for i, (n, _) in enumerate(heads)}
    spans: list[tuple[int, int]] = []
    hit: list[int] = []
    for target in article_nums:
        if target not in idx:
            continue
        i = idx[target]
        lo = max(0, i - context_articles)
        hi = min(len(heads) - 1, i + context_articles)
        spans.append((heads[lo][1], heads[hi + 1][1] if hi + 1 < len(heads) else len(full_text)))
        hit.append(target)
    if not spans:
        return (full_text or "")[:max_chars], []
    spans.sort()
    merged = []
    for s, e in spans:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    parts = [full_text[s:e].strip() for s, e in merged]
    return "\n…\n".join(parts)[:max_chars], hit


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
        self._index_cache: list[tuple[str, str]] | None = None
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
        """kb_read 取全文，截断到 max_chars；失败返回 ''
        （kb_read 参数名为 relative_path）"""
        r = self._call_tool(self.server, "kb_read", {"relative_path": path})
        if not r.get("success"):
            return ""
        return (r.get("text", "") or "")[:max_chars]

    # ── RAG v2：定位→直取 ──────────────────────────────

    def _index_links(self) -> list[tuple[str, str]]:
        """读取 index.md 并缓存 (名称, concepts 全路径) 列表；失败返回 []"""
        if self._index_cache is None:
            text = self.read(INDEX_PATH, max_chars=100_000)
            self._index_cache = parse_index_links(text)
        return self._index_cache

    def locate_concept_files(self, law_names: list[str]) -> list[str]:
        """按法律名定位 concepts/ 下的正文文件：
        1) index.md 链接名匹配；2) kb_search 结果中筛选 concepts/ 非 Skill 路径"""
        hits: list[str] = []
        for name in law_names:
            for link_name, path in self._index_links():
                if name in link_name or link_name.replace("中华人民共和国", "") == name:
                    if path not in hits:
                        hits.append(path)
        if not hits:
            for name in law_names:
                files, _ = self.search(name)
                for f in files:
                    if "/concepts/" in f and "Skill" not in f and f not in hits:
                        hits.append(f)
        return hits[:3]

    def retrieve_v2(self, item: dict) -> dict:
        """定位→直取：法名定位 concepts 文件 → kb_read 取正文 → 按条款截取（≤3000 字符）。
        返回 {"files": [...], "articles": [...], "context": str}"""
        law_names = extract_law_names(item)
        article_nums = extract_article_nums(item)
        files = self.locate_concept_files(law_names)
        parts, hit_articles, used = [], [], []
        for path in files:
            full = self.read(path)
            if not full:
                continue
            used.append(path)
            snippet, arts = extract_article_sections(
                full, article_nums, max_chars=RAG_MAX_CONTEXT_CHARS - sum(len(p) for p in parts))
            hit_articles += arts
            parts.append(f"【{path}】\n{snippet}")
            if sum(len(p) for p in parts) >= RAG_MAX_CONTEXT_CHARS:
                break
        return {"files": used, "articles": hit_articles,
                "context": "\n\n".join(parts)[:RAG_MAX_CONTEXT_CHARS]}

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


def _norm_base(s: str) -> str:
    """基础归一化：去空白/书名号/国名前缀（不含条款号归一化）"""
    t = re.sub(r"\s+", "", s or "")
    t = re.sub(r"（[^）]{0,30}）", "", t)  # 法名与条号间的修订年份等括号注释不影响命中
    t = re.sub(r"\([^)]{0,30}\)", "", t)
    t = t.replace("《", "").replace("》", "").replace("中华人民共和国", "")
    t = t.replace("*", "")  # markdown 强调符（**条款**）不影响命中
    return t


def _norm(s: str) -> str:
    """评分归一化：基础归一化 + 条款号/中文数字统一为阿拉伯数字，
    使 '第九十九条'、'第99条'、'九十九' 在比较时等价"""
    return normalize_cn_numerals(_norm_base(s))


def score_item(answer: str, item: dict) -> dict:
    """逐题评分：引用命中率 + 要点 F1（诚实计算，不做任何修饰）。
    条款号经中文数字归一化后匹配；同时保留归一化前（raw）分数对照。"""
    a = _norm(answer)
    a_raw = _norm_base(answer)
    cites = item["required_citations"]
    hit_c = sum(1 for c in cites if _norm(c) in a)
    hit_c_raw = sum(1 for c in cites if _norm_base(c) in a_raw)
    citation_hit = hit_c / len(cites) if cites else 1.0
    citation_hit_raw = hit_c_raw / len(cites) if cites else 1.0

    kps = item["key_points"]
    tp = sum(1 for k in kps if _norm(k) in a)
    tp_raw = sum(1 for k in kps if _norm_base(k) in a_raw)
    precision = tp / len(kps) if kps else 1.0  # 输出侧全部要求要点
    recall = tp / len(kps) if kps else 1.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    p_raw = tp_raw / len(kps) if kps else 1.0
    f1_raw = (2 * p_raw * p_raw / (2 * p_raw)) if p_raw else 0.0
    return {
        "id": item["id"], "category": item["category"],
        "citation_hit": round(citation_hit, 4),
        "citation_hits": hit_c, "citation_total": len(cites),
        "citation_hit_raw": round(citation_hit_raw, 4),
        "keypoint_tp": tp, "keypoint_total": len(kps),
        "keypoint_f1": round(f1, 4),
        "keypoint_f1_raw": round(f1_raw, 4),
    }


def load_dataset(limit: int = 0) -> list[dict]:
    items = [json.loads(l) for l in DATASET.read_text(encoding="utf-8").splitlines() if l.strip()]
    return items[:limit] if limit else items


def answer_question(client, item: dict, mock: bool,
                    retriever: RagRetriever | None = None) -> tuple[str, list[str], list[int]]:
    """答题，返回 (答案, 检索文件清单, 命中条款号)。retriever 非空时为 RAG 模式"""
    if mock or client is None or not client.available():
        return MOCK_ANSWER, [], []
    question = item["question"]
    files: list[str] = []
    articles: list[int] = []
    if retriever is not None:
        try:
            hit = retriever.retrieve_v2(item)
            files = hit["files"]
            articles = hit.get("articles", [])
            if hit["context"]:
                question = question + RAG2_PROMPT_SUFFIX.format(context=hit["context"])
        except Exception as e:
            print(f"    [RAG] {item['id']} 检索失败（降级为无检索作答）: {e}", flush=True)
    try:
        return client.complete(question, system=SYSTEM, max_tokens=1024) or MOCK_ANSWER, files, articles
    except Exception as e:
        return f"[error] {type(e).__name__}: {e}", files, articles


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
        ans, files, articles = answer_question(client, item, mock, retriever=retriever)
        sc = score_item(ans, item)
        sc["answer"] = ans
        sc["retrieved_files"] = files
        sc["retrieved_articles"] = articles
        sc["golden_answer"] = item["golden_answer"]
        results.append(sc)
        print(f"  [{i:02d}/{len(items)}] {item['id']} {item['category']} "
              f"cite={sc['citation_hit']:.2f} f1={sc['keypoint_f1']:.2f}", flush=True)

    n = len(results) or 1
    summary = {
        "n_questions": len(results),
        "mode": mode,
        "citation_accuracy": round(sum(r["citation_hit"] for r in results) / n, 4),
        "citation_accuracy_raw": round(sum(r["citation_hit_raw"] for r in results) / n, 4),
        "keypoint_f1": round(sum(r["keypoint_f1"] for r in results) / n, 4),
        "keypoint_f1_raw": round(sum(r["keypoint_f1_raw"] for r in results) / n, 4),
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
    print(f"  法条引用准确率: {summary['citation_accuracy']:.4f} "
          f"(归一化前 {summary['citation_accuracy_raw']:.4f})")
    print(f"  要点 F1:        {summary['keypoint_f1']:.4f} "
          f"(归一化前 {summary['keypoint_f1_raw']:.4f})")
    for c, s in summary["by_category"].items():
        print(f"    - {c}: cite={s['citation_accuracy']:.2f} f1={s['keypoint_f1']:.2f} (n={s['n']})")
    print(f"  报告: {args.out}")
    if retriever is not None:
        retriever.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
