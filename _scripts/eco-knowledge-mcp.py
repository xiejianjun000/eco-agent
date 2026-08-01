#!/usr/bin/env python3
"""eco-knowledge-mcp — ECO AGENT 法规知识库 MCP 服务

MCP 协议（JSON-RPC 2.0 over stdio）实现。
桥接 FlowWiki Obsidian Vault，提供法规检索、溯源、图谱查询功能。

协议：JSON-RPC 2.0
传输：stdin/stdout
"""

import json
import sys
import os
import re
import time
from pathlib import Path
from datetime import datetime

# rag_score 忠实度核验（vendored，agent_core 内；numpy 缺失时优雅降级）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    from agent_core.rag_score import RAGScorer
    _SCORER = RAGScorer()
except Exception:
    _SCORER = None

# ===== 配置 =====

# Obsidian Vault 路径（自动检测 + 环境变量覆盖）
_DEFAULT_VAULTS = [
    os.path.expanduser("~/Documents/Obsidian Vault"),
    os.path.expanduser("~\\Documents\\Obsidian Vault"),
    "C:\\Users\\Administrator\\Documents\\Obsidian Vault",
    "/c/Users/Administrator/Documents/Obsidian Vault",
]

OBSIDIAN_VAULT = os.environ.get("OBSIDIAN_VAULT", "")
if not OBSIDIAN_VAULT or not os.path.isdir(OBSIDIAN_VAULT):
    for p in _DEFAULT_VAULTS:
        if os.path.isdir(os.path.join(p, "raw")):
            OBSIDIAN_VAULT = p
            break
    else:
        OBSIDIAN_VAULT = _DEFAULT_VAULTS[0]

# ===== 工具定义 =====

TOOLS = [
    {
        "name": "eco_search",
        "description": "检索生态环境法规知识库（FlowWiki），支持关键词搜索和全文本检索",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词（支持多个用空格分隔）"
                },
                "scope": {
                    "type": "string",
                    "enum": ["all", "wiki", "raw"],
                    "description": "搜索范围：wiki（知识层）、raw（原文层）、all（全部）",
                    "default": "all"
                },
                "max_results": {
                    "type": "integer",
                    "description": "最大返回结果数",
                    "default": 10,
                    "maximum": 30
                },
                "env_tag": {
                    "type": "string",
                    "description": "环境要素过滤（如 env/air, env/water, env/soil）",
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "eco_retrieve",
        "description": "获取指定法规或知识条目的详细内容",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "文件路径（相对 vault 根目录，如 wiki/01_生态环境/大气污染防治.md）"
                },
                "statute_name": {
                    "type": "string",
                    "description": "法规名称（如 大气污染防治法、生态环境法典），与 path 二选一"
                }
            }
        }
    },
    {
        "name": "eco_statute_query",
        "description": "按法规名称查询具体条文内容",
        "input_schema": {
            "type": "object",
            "properties": {
                "statute": {
                    "type": "string",
                    "description": "法规名称（如 大气污染防治法）"
                },
                "article": {
                    "type": "string",
                    "description": "条文号（如 第X条、第X章、第X节），可选"
                }
            },
            "required": ["statute"]
        }
    },
    {
        "name": "eco_graph_query",
        "description": "查询法规知识图谱，获取某法规或要素的关联关系",
        "input_schema": {
            "type": "object",
            "properties": {
                "node": {
                    "type": "string",
                    "description": "知识图谱节点名称（如法规名、要素名）"
                },
                "relation_type": {
                    "type": "string",
                    "enum": ["all", "references", "referenced_by", "related"],
                    "description": "关联类型",
                    "default": "all"
                }
            },
            "required": ["node"]
        }
    },
    {
        "name": "eco_list_statutes",
        "description": "列出指定环境要素或分类下的所有法规",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "分类（如 大气、水、土壤、固废、噪声、放射性、生态保护、海洋）"
                },
                "scope": {
                    "type": "string",
                    "enum": ["raw", "wiki"],
                    "default": "raw"
                }
            },
            "required": ["category"]
        }
    },
    {
        "name": "eco_faithfulness_check",
        "description": "答案忠实度核验：对照法规原文检查答案是否有原文支撑，输出忠实度/幻觉风险评分（幻觉预警，D12 反幻觉抓手）",
        "input_schema": {
            "type": "object",
            "properties": {
                "answer": {
                    "type": "string",
                    "description": "待核验的答案文本"
                },
                "source": {
                    "type": "string",
                    "description": "对照原文（直接给文本）；与 statute 二选一"
                },
                "statute": {
                    "type": "string",
                    "description": "法规名称（如 大气污染防治法），自动从 vault 取原文对照"
                },
                "query": {
                    "type": "string",
                    "description": "原始问题（可选，用于相关性/完整性评分）"
                }
            },
            "required": ["answer"]
        }
    }
]

# ===== 核心检索函数 =====


def find_vault_path():
    """定位 Obsidian Vault 路径"""
    vault = Path(OBSIDIAN_VAULT)
    if vault.exists() and (vault / "raw").exists():
        return vault
    return vault


_FILE_LIST_CACHE: dict = {}


def _cached_files(root, ttl: float = 300.0):
    """目录文件清单缓存：服务进程常驻，避免每次调用对 11 万文件的 vault 重新 rglob。
    ttl 秒内的重复调用直接复用上次的清单。"""
    key = str(root)
    hit = _FILE_LIST_CACHE.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    files = [f for f in root.rglob("*") if f.suffix.lower() in (".md", ".txt") and f.is_file()]
    _FILE_LIST_CACHE[key] = (time.time(), files)
    return files


def search_in_files(file_paths, query, max_results=10):
    """两轮检索：先文件名命中（不读内容，快），再对剩余文件做内容命中（读前 50KB）。
    关键词评分逻辑不变；文件名命中加 1.0 权重排在内容命中之前。"""
    keywords = query.lower().split()
    if not keywords:
        return []
    vault = find_vault_path()

    def _rel(fpath):
        return str((fpath.relative_to(vault) if vault in fpath.parents else fpath).as_posix())

    def _make_hit(fpath, content, boost):
        content_lower = content.lower()
        match_count = sum(1 for kw in keywords if kw in content_lower)
        frontmatter = extract_frontmatter(content)
        return {
            "path": _rel(fpath),
            "score": boost + match_count / len(keywords),
            "title": frontmatter.get("title", fpath.stem),
            "snippet": extract_snippet(content, keywords, max_length=300),
            "tags": frontmatter.get("tags", []),
            "updated": frontmatter.get("updated", ""),
        }

    results = []
    remaining = []
    for fpath in file_paths:
        if len(results) >= max_results:
            break
        if any(kw in fpath.stem.lower() for kw in keywords):
            try:
                with open(fpath, encoding='utf-8', errors='ignore') as f:
                    results.append(_make_hit(fpath, f.read(50000), boost=1.0))
            except OSError:
                pass
        else:
            remaining.append(fpath)

    for fpath in remaining:
        if len(results) >= max_results:
            break
        try:
            with open(fpath, encoding='utf-8', errors='ignore') as f:
                content = f.read(50000)
            if not any(kw in content.lower() for kw in keywords):
                continue
            results.append(_make_hit(fpath, content, boost=0.0))
        except OSError:
            continue

    # 按评分排序（文件名命中经 boost 排在前面）
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:max_results]


def extract_snippet(content, keywords, max_length=300):
    """提取关键词周围的上下文片段"""
    content_lower = content.lower()
    # 跳过 frontmatter
    body_start = content.find("---", 2)
    if body_start != -1:
        body_start = content.find("\n", body_start) + 1
        body = content[body_start:]
    else:
        body = content

    body_lower = body.lower()
    # 找第一个关键词位置
    first_pos = -1
    for kw in keywords:
        pos = body_lower.find(kw)
        if pos != -1 and (first_pos == -1 or pos < first_pos):
            first_pos = pos

    if first_pos == -1:
        return body[:max_length].strip()

    start = max(0, first_pos - 100)
    end = min(len(body), first_pos + 200)
    snippet = body[start:end].strip()
    if start > 0:
        snippet = "..." + snippet
    if end < len(body):
        snippet = snippet + "..."
    return snippet[:max_length]


def extract_frontmatter(content):
    """提取 YAML frontmatter"""
    fm = {}
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            yaml_text = content[3:end]
            for line in yaml_text.strip().split("\n"):
                if ":" in line:
                    key, _, value = line.partition(":")
                    key = key.strip()
                    value = value.strip()
                    # 解析列表
                    if value.startswith("["):
                        try:
                            value = json.loads(value)
                        except json.JSONDecodeError:
                            value = [v.strip().strip('"\'') for v in value.strip("[]").split(",")]
                    else:
                        value = value.strip('"\'')
                    fm[key] = value
    return fm


def collect_wiki_files(vault_root):
    """收集 wiki/ 目录下所有 .md 文件"""
    return list((vault_root / "wiki").rglob("*.md"))


def collect_raw_files(vault_root, category=None):
    """收集 raw/ 目录下法规文件：递归全部子目录（vault 真实结构含 inbox/、
    china_eia_articles/、排污许可执行报告/ 等，不再依赖硬编码的 01_ 五分类），
    同时纳入 .txt（部分原文以 txt 入仓）"""
    raw_root = vault_root / "raw"
    if not raw_root.exists():
        return []
    files = _cached_files(raw_root)
    if category:
        c = category.lower()
        matched = [f for f in files if c in f.stem.lower() or c in f.parent.name.lower()]
        return matched
    return files


def find_statute_file(vault_root, statute_name):
    """按法规名称查找对应文件"""
    # 空名或含 glob 元字符的名称直接判未找到，避免拼出非法 glob 模式（如 **/**.md）
    name = re.sub(r"[*?\[\]/]", "", str(statute_name or "")).strip()
    if not name:
        return None
    # 先搜 wiki/
    for pattern in [
        f"wiki/**/*{name}*.md",
        f"wiki/**/{name}*.md",
    ]:
        matches = list(vault_root.glob(pattern))
        if matches:
            return matches[0]

    # 再搜 raw/
    for pattern in [
        f"raw/**/*{name}*.md",
        f"raw/**/{name}*.md",
    ]:
        matches = list(vault_root.glob(pattern))
        if matches:
            return matches[0]

    return None


def extract_article(content, article=None):
    """从法规内容中提取指定条文"""
    if not article:
        # 返回文件前 2000 字作为摘要
        body = content
        fm_end = content.find("---", 2)
        if fm_end != -1:
            body_start = content.find("\n", fm_end) + 1
            body = content[body_start:]
        return body[:2000].strip()

    # 搜索具体条文
    pattern = re.compile(rf"(##?\s*{re.escape(article)}[\s\S]*?)(?=##?\s*第|\Z)", re.IGNORECASE)
    match = pattern.search(content)
    if match:
        return match.group(1).strip()
    return None


# ===== MCP 协议处理 =====


def _std_tools() -> list:
    """标准 MCP 工具表：官方 SDK 识别 inputSchema 键（本服务内部沿用 input_schema）"""
    return [{"name": t["name"], "description": t["description"],
             "inputSchema": t.get("input_schema") or t.get("inputSchema") or {}} for t in TOOLS]


def handle_request(request):
    """处理 JSON-RPC 2.0 请求（标准 MCP 方法 + mcp.* 历史方言别名）"""
    req_id = request.get("id")
    method = request.get("method", "")
    params = request.get("params", {})

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": params.get("protocolVersion", "2024-11-05"),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "eco-knowledge-mcp", "version": "0.2.0"},
            },
        }

    elif method in ("tools/list", "mcp.list_tools"):
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": _std_tools()}
        }

    elif method in ("tools/call", "mcp.call_tool"):
        tool_name = params.get("name", "")
        tool_args = params.get("arguments", {})
        return handle_tool_call(req_id, tool_name, tool_args)

    elif method in ("ping", "mcp.ping"):
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"status": "ok", "timestamp": datetime.now().isoformat()}
        }

    else:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method '{method}' not found"}
        }


def handle_tool_call(req_id, tool_name, args):
    """处理工具调用"""
    vault = find_vault_path()

    try:
        if tool_name == "eco_search":
            query = args.get("query", "")
            scope = args.get("scope", "all")
            max_results = min(args.get("max_results", 10), 30)
            env_tag = args.get("env_tag", "")

            results = []
            if scope in ("all", "wiki"):
                wiki_files = collect_wiki_files(vault)
                wiki_results = search_in_files(wiki_files, query, max_results)
                for r in wiki_results:
                    r["source"] = "wiki"
                    # 环境要素过滤
                    if env_tag:
                        tags = r.get("tags", [])
                        if isinstance(tags, str):
                            tags = [tags]
                        if env_tag not in tags:
                            continue
                    results.append(r)

            if scope in ("all", "raw") and len(results) < max_results:
                raw_files = collect_raw_files(vault)
                raw_results = search_in_files(raw_files, query, max_results - len(results))
                for r in raw_results:
                    r["source"] = "raw"
                    results.append(r)

            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps({
                                "query": query,
                                "total_results": len(results),
                                "results": results
                            }, ensure_ascii=False, indent=2)
                        }
                    ]
                }
            }

        elif tool_name == "eco_retrieve":
            file_path = args.get("path", "")
            statute_name = args.get("statute_name", "")

            target_path = None
            if file_path:
                target_path = vault / file_path
                if not target_path.exists():
                    target_path = vault / "wiki" / file_path
                if not target_path.exists():
                    target_path = vault / "raw" / file_path

            elif statute_name:
                target_path = find_statute_file(vault, statute_name)

            if not target_path or not target_path.exists():
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32000, "message": f"未找到: {file_path or statute_name}"}
                }

            try:
                with open(target_path, encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": f"## {target_path.name}\n\n```markdown\n{content[:10000]}\n```\n\n*（显示前 10000 字符，全文共 {len(content)} 字符）*"
                            }
                        ]
                    }
                }
            except OSError as e:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32000, "message": f"读取失败: {e}"}
                }

        elif tool_name == "eco_statute_query":
            # 容错：模型常误传 keyword/query 作法规名，兜底兼容
            statute = args.get("statute") or args.get("keyword") or args.get("query", "")
            article = args.get("article", "")

            target_path = find_statute_file(vault, statute)
            if not target_path:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32000, "message": f"未找到法规: {statute}"}
                }

            with open(target_path, encoding='utf-8', errors='ignore') as f:
                content = f.read()

            if article:
                article_content = extract_article(content, article)
                if article_content:
                    result_text = f"## {statute} {article}\n\n{article_content}"
                else:
                    result_text = f"未在 {statute} 中找到 {article}，以下是全文摘要：\n\n{extract_article(content)}"
            else:
                result_text = f"## {statute}（概览）\n\n{extract_article(content)}"
                # 添加章节导航
                chapters = re.findall(r'^##\s+(.+)$', content, re.MULTILINE)
                if chapters:
                    result_text += "\n\n### 章节结构\n\n" + "\n".join(f"- {c}" for c in chapters[:30])

            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": result_text}]
                }
            }

        elif tool_name == "eco_graph_query":
            node = args.get("node", "")
            relation_type = args.get("relation_type", "all")

            # 基于 wiki 文件间的 wikilink 进行图谱分析
            wiki_files = collect_wiki_files(vault)
            related = []

            node_lower = node.lower()

            for wf in wiki_files:
                try:
                    with open(wf, encoding='utf-8', errors='ignore') as f:
                        content = f.read()

                    # 检查是否引用了目标节点
                    links = re.findall(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]', content)
                    for link in links:
                        if node_lower in link.lower():
                            rel_path = wf.relative_to(vault).as_posix()
                            related.append({
                                "file": rel_path,
                                "relation": "references",
                                "target": link.strip()
                            })

                    # 检查目标节点是否引用了本文件
                    if node_lower in wf.stem.lower():
                        for link in links:
                            rel_path = wf.relative_to(vault).as_posix()
                            related.append({
                                "file": rel_path,
                                "relation": "referenced_by",
                                "target": link.strip()
                            })
                except OSError:
                    continue

            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps({
                                "node": node,
                                "relations_count": len(related),
                                "relations": related[:30]
                            }, ensure_ascii=False, indent=2)
                        }
                    ]
                }
            }

        elif tool_name == "eco_list_statutes":
            category = args.get("category", "")
            scope = args.get("scope", "raw")

            if scope == "wiki":
                root_dir = vault / "wiki"
            else:
                root_dir = vault / "raw"

            if not root_dir.exists():
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32000, "message": f"目录不存在: {root_dir}"}
                }

            # 搜索所有 .md/.txt 文件（走清单缓存），按文件名筛选
            all_files = _cached_files(root_dir)
            matched = []
            for f in all_files:
                if category.lower() in f.stem.lower():
                    rel_path = f.relative_to(vault).as_posix()
                    matched.append({
                        "path": rel_path,
                        "name": f.stem,
                        "dir": f.parent.relative_to(vault).as_posix()
                    })

            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps({
                                "category": category,
                                "total": len(matched),
                                "statutes": matched
                            }, ensure_ascii=False, indent=2)
                        }
                    ]
                }
            }

        elif tool_name == "eco_faithfulness_check":
            # 答案忠实度核验：答案 claims 对照法规原文，输出幻觉风险（D12 抓手）
            if _SCORER is None:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32000, "message": "rag_score 不可用（numpy 缺失或导入失败）"}
                }

            answer = args.get("answer", "")
            source = args.get("source", "")
            statute = args.get("statute", "")
            query = args.get("query", "") or answer[:50]

            if not answer.strip():
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32602, "message": "answer 不能为空"}
                }

            contexts = []
            if source.strip():
                contexts.append(source)
            if statute.strip():
                target_path = find_statute_file(vault, statute)
                if not target_path:
                    return {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {"code": -32000, "message": f"未找到法规: {statute}"}
                    }
                with open(target_path, encoding='utf-8', errors='ignore') as f:
                    contexts.append(f.read(100000))
            if not contexts:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32602, "message": "必须提供 source（内联原文）或 statute（法规名）之一"}
                }

            r = _SCORER.score(query, answer, contexts)
            risk = "low" if r.is_low_risk else ("medium" if r.is_medium_risk else "high")
            d = r.to_dict()
            d["risk_level"] = risk
            d["verdict_note"] = {
                "low": "答案 claims 有原文支撑，幻觉风险低",
                "medium": "部分 claims 缺乏原文支撑，建议人工复核后交付",
                "high": "大量 claims 无原文支撑，疑似幻觉，禁止直接交付",
            }[risk]
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(d, ensure_ascii=False, indent=2)}]
                }
            }

        else:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"}
            }

    except Exception as e:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32000, "message": f"Internal error: {str(e)}"}
        }


# ===== 主循环 =====


def main():
    """MCP 服务器主循环：从 stdin 读取 JSON-RPC 请求，处理，写入 stdout"""
    # 启动信息走 stderr，避免污染 stdout 的 JSON-RPC 帧（官方 MCP SDK 客户端会被打乱）
    startup_msg = json.dumps({
        "event": "mcp.startup",
        "server_name": "eco-knowledge-mcp",
        "version": "0.2.0",
        "vault_path": str(find_vault_path()),
        "tools_count": len(TOOLS)
    }, ensure_ascii=False)
    sys.stderr.write(startup_msg + "\n")
    sys.stderr.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            error_resp = json.dumps({
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "Parse error"}
            })
            sys.stdout.write(error_resp + "\n")
            sys.stdout.flush()
            continue

        # JSON-RPC 通知（无 id，如 notifications/initialized）只处理不回包
        if "id" not in request:
            continue

        response = handle_request(request)
        resp_str = json.dumps(response, ensure_ascii=False)
        sys.stdout.write(resp_str + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        # 客户端断开（管道关闭）属正常退出路径，重定向 stdout 避免解释器收尾再报错
        import os
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        sys.exit(0)
