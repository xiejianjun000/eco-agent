#!/usr/bin/env python3
"""
memory_tree.py — eco Agent Memory Tree 核心引擎

评分制记忆树，实现 SQLite 持久化 + Obsidian 双向同步 + 混合检索。

用法：
  from _scripts.memory_tree import MemoryTree
  mt = MemoryTree()

  # 创建节点
  node = mt.create_node(type='case', title='XX公司超标案', content='...',
                         tags=['env/air', 'enforcement/penalty'])

  # 检索
  results = mt.search('超标排放 大气')

  # 同步到 Obsidian
  mt.sync_to_obsidian()
"""

import os
import json
import re
import time
import hashlib
import sqlite3
import logging
from pathlib import Path
from datetime import datetime
from typing import Any

logger = logging.getLogger("memory_tree")

# ===== 配置 =====
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "memory-tree" / "data" / "eco_memory.db"
OBSIDIAN_SYNC_DIR = PROJECT_ROOT / "memory-tree" / "obsidian_sync"
OBSIDIAN_VAULT = None  # 由 set_obsidian_vault() 设置


class MemoryTree:
    """Memory Tree 核心引擎"""

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        logger.info(f"Memory Tree 初始化完成: {self.db_path}")

    # ── 数据库初始化 ──

    def _init_db(self):
        """初始化数据库和 Schema"""
        schema_path = PROJECT_ROOT / "memory-tree" / "ECO_SCHEMA.sql"
        if schema_path.exists():
            sql = schema_path.read_text(encoding="utf-8")
            with self._conn() as conn:
                conn.executescript(sql)
            logger.info("数据库 Schema 已加载")
        else:
            logger.warning(f"Schema 文件不存在: {schema_path}")

    def _conn(self) -> sqlite3.Connection:
        """获取数据库连接"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    # ── 节点 CRUD ──

    def create_node(self, type: str, title: str, content: str,
                    tags: list[str] = None, score: float = 50.0,
                    parent_id: str = None, source: str = "manual",
                    confidence: str = "medium") -> dict[str, Any]:
        """创建新节点"""
        node_id = self._generate_id(type)
        tags_json = json.dumps(tags or [], ensure_ascii=False)
        now = datetime.now().isoformat()

        with self._conn() as conn:
            conn.execute("""
                INSERT INTO nodes (id, type, title, content, score, tags,
                                   parent_id, source, confidence,
                                   created_at, updated_at, accessed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (node_id, type, title, content, score, tags_json,
                  parent_id, source, confidence, now, now, now))

            # 更新 FTS 索引
            conn.execute("""
                INSERT INTO nodes_fts (rowid, title, content, tags)
                VALUES (last_insert_rowid(), ?, ?, ?)
            """, (title, content[:5000], tags_json))

            # 如果有父节点，创建关联边
            if parent_id:
                conn.execute("""
                    INSERT INTO edges (source_id, target_id, relation, weight)
                    VALUES (?, ?, 'derived_from', 0.8)
                """, (node_id, parent_id))

            # 更新元数据
            conn.execute("""
                UPDATE metadata SET value = (
                    SELECT COUNT(*) FROM nodes
                ) WHERE key = 'node_count'
            """)

        logger.info(f"节点创建成功: {node_id} ({type}) - {title[:30]}")
        return self.get_node(node_id)

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        """获取节点详情"""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM nodes WHERE id = ?", (node_id,)
            ).fetchone()
            if not row:
                return None
            node = dict(row)
            node["tags"] = json.loads(node.get("tags", "[]"))
            # 更新访问计数
            conn.execute("""
                UPDATE nodes SET access_count = access_count + 1,
                                 accessed_at = datetime('now')
                WHERE id = ?
            """, (node_id,))
            return node

    def update_node(self, node_id: str, **kwargs) -> dict[str, Any] | None:
        """更新节点属性"""
        allowed = {"title", "content", "score", "tags", "confidence", "parent_id"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}

        if not updates:
            return self.get_node(node_id)

        with self._conn() as conn:
            # 更新 tags 为 JSON
            if "tags" in updates and isinstance(updates["tags"], list):
                updates["tags"] = json.dumps(updates["tags"], ensure_ascii=False)

            # 构建 SET 子句
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            values = list(updates.values()) + [node_id]

            conn.execute(f"UPDATE nodes SET {set_clause} WHERE id = ?", values)

            # 更新 FTS
            if "title" in updates or "content" in updates:
                row = conn.execute(
                    "SELECT rowid, title, content, tags FROM nodes WHERE id = ?",
                    (node_id,)
                ).fetchone()
                if row:
                    conn.execute("""
                        INSERT INTO nodes_fts (rowid, title, content, tags)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(rowid) DO UPDATE SET
                            title=excluded.title, content=excluded.content, tags=excluded.tags
                    """, (row["rowid"], updates.get("title", row["title"]),
                          updates.get("content", row["content"][:5000]),
                          updates.get("tags", row["tags"])))

        return self.get_node(node_id)

    def delete_node(self, node_id: str) -> bool:
        """删除节点及其关联"""
        with self._conn() as conn:
            row = conn.execute("SELECT rowid FROM nodes WHERE id = ?", (node_id,)).fetchone()
            if not row:
                return False
            conn.execute("DELETE FROM nodes_fts WHERE rowid = ?", (row["rowid"],))
            conn.execute("DELETE FROM edges WHERE source_id = ? OR target_id = ?",
                         (node_id, node_id))
            conn.execute("DELETE FROM sync_log WHERE node_id = ?", (node_id,))
            conn.execute("DELETE FROM nodes WHERE id = ?", (node_id,))
            conn.execute("UPDATE metadata SET value = (SELECT COUNT(*) FROM nodes) WHERE key = 'node_count'")
        logger.info(f"节点已删除: {node_id}")
        return True

    def list_nodes(self, type: str | None = None, tags: list[str] | None = None,
                   limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        """列出节点，支持类型和标签过滤"""
        where_clauses = []
        params = []

        if type:
            where_clauses.append("n.type = ?")
            params.append(type)
        if tags:
            for tag in tags:
                where_clauses.append("n.tags LIKE ?")
                params.append(f"%{tag}%")

        where = " AND ".join(where_clauses) if where_clauses else "1=1"

        with self._conn() as conn:
            rows = conn.execute(f"""
                SELECT n.*, COUNT(e.id) as edge_count
                FROM nodes n
                LEFT JOIN edges e ON e.source_id = n.id OR e.target_id = n.id
                WHERE {where}
                GROUP BY n.id
                ORDER BY n.score DESC, n.updated_at DESC
                LIMIT ? OFFSET ?
            """, params + [limit, offset]).fetchall()

            results = []
            for row in rows:
                node = dict(row)
                node["tags"] = json.loads(node.get("tags", "[]"))
                results.append(node)
            return results

    # ── 检索 ──

    def search(self, query: str, type: str | None = None,
               max_results: int = 10) -> list[dict[str, Any]]:
        """混合检索（BM25 + 评分排序 + LIKE 降级）"""
        keywords = query.lower().split()
        if not keywords:
            return []

        # 检测是否含中文（中文用 LIKE 降级为主）
        has_chinese = any('一' <= c <= '鿿' for c in query)

        with self._conn() as conn:
            where_type = f"AND n.type = '{type}'" if type else ""
            results = []

            if not has_chinese:
                # FTS5 BM25 检索（仅对非中文有效）
                fts_query = " OR ".join(keywords)
                try:
                    rows = conn.execute(f"""
                        SELECT n.*, nodes_fts.rank as bm25_score,
                               COUNT(e.id) as edge_count
                        FROM nodes_fts
                        JOIN nodes n ON n.rowid = nodes_fts.rowid
                        LEFT JOIN edges e ON e.source_id = n.id OR e.target_id = n.id
                        WHERE nodes_fts MATCH ?
                        {where_type}
                        GROUP BY n.id
                        ORDER BY nodes_fts.rank ASC
                        LIMIT ?
                    """, (fts_query, max_results)).fetchall()
                    results = [dict(r) for r in rows]
                except sqlite3.OperationalError:
                    pass

            # LIKE 降级检索（对中文或 FTS 结果不足时）
            if len(results) < max_results:
                remaining = max_results - len(results)
                existing_ids = {r["id"] for r in results}
                for kw in keywords[:3]:  # 最多用 3 个关键词
                    if remaining <= 0:
                        break
                    exclude_clause = ""
                    params = [f"%{kw}%", f"%{kw}%"]
                    if existing_ids:
                        placeholders = ','.join('?' for _ in existing_ids)
                        exclude_clause = f"AND n.id NOT IN ({placeholders})"
                        params.extend(list(existing_ids))
                    params.append(f"%{kw}%")
                    params.append(remaining)

                    rows = conn.execute(f"""
                        SELECT n.*, COUNT(e.id) as edge_count
                        FROM nodes n
                        LEFT JOIN edges e ON e.source_id = n.id OR e.target_id = n.id
                        WHERE (n.title LIKE ? OR n.content LIKE ?)
                        {where_type}
                        {exclude_clause}
                        GROUP BY n.id
                        ORDER BY
                            CASE
                                WHEN n.title LIKE ? THEN 3
                                ELSE 1
                            END DESC,
                            n.score DESC
                        LIMIT ?
                    """, params)

                    for row in rows:
                        node = dict(row)
                        node["tags"] = json.loads(node.get("tags", "[]"))
                        node["snippet"] = self._generate_snippet(
                            node.get("content", ""), [kw]
                        )
                        results.append(node)
                        existing_ids.add(node["id"])
                        remaining -= 1

            # 生成摘要
            for r in results:
                if "snippet" not in r and "content" in r:
                    r["snippet"] = self._generate_snippet(r["content"], keywords)
                r.pop("bm25_score", None)
                if isinstance(r.get("tags"), str):
                    r["tags"] = json.loads(r["tags"])

            return results[:max_results]

    def search_hybrid(self, query: str, type: str | None = None,
                      max_results: int = 10) -> list[dict[str, Any]]:
        """Phase B2 混合检索：关键词通道（FTS5 BM25/LIKE，复用 search）+ 向量通道
        （hybrid_retrieval，OpenAI 兼容 embedding，sqlite 本地向量库）RRF(k=60) 融合。
        无 embedding 配置/调用失败时优雅降级为纯关键词通道（结果 channel='bm25'）。
        每个结果附 'channel' 与 'rrf_score' 来源标注。"""
        kw_hits = self.search(query, type=type, max_results=max_results * 2)
        kw_rank = [h["id"] for h in kw_hits]
        by_id = {h["id"]: h for h in kw_hits}
        vec_rank: list[str] = []
        channel = "bm25"
        try:
            from agent_core.hybrid_retrieval import EmbeddingClient, VectorStore, rrf_fuse
            ec = EmbeddingClient()
            if ec.available():
                with self._conn() as conn:
                    rows = conn.execute(
                        "SELECT id, title, content, type FROM nodes").fetchall()
                store = VectorStore()
                namespace = "memory_tree"
                fids = [f"{namespace}:{r['id']}" for r in rows]
                missing_idx = [i for i, f in enumerate(fids)
                               if f not in store.existing_ids(fids)]
                if missing_idx:
                    vecs = ec.embed([f"{rows[i]['title']}\n{rows[i]['content']}"[:2000]
                                     for i in missing_idx])
                    if vecs:
                        for i, vec in zip(missing_idx, vecs, strict=False):
                            if vec:
                                store.upsert(fids[i], vec,
                                             source=f"memory_tree:{rows[i]['type']}",
                                             text=rows[i]["content"])
                qvec = ec.embed([query[:2000]])
                if qvec and qvec[0]:
                    if type:
                        allow = {f"{namespace}:{r['id']}" for r in rows if r["type"] == type}
                    else:
                        allow = set(fids)
                    vec_rank = [d.split(":", 1)[1]
                                for d in store.cosine_rank(qvec[0], doc_ids=list(allow),
                                                           top_k=max_results * 2)]
                    if vec_rank:
                        channel = "hybrid"
                        # 向量命中的节点补充进候选集（关键词通道可能漏召回）
                        for nid in vec_rank:
                            if nid not in by_id:
                                node = self.get_node(nid)
                                if node:
                                    by_id[nid] = node
            fused = rrf_fuse([kw_rank] + ([vec_rank] if vec_rank else []))
        except Exception:
            # 混合检索不可用：按关键词通道名次手工计算 RRF 分，保证结果结构一致
            fused = [(nid, 1.0 / (60 + i)) for i, nid in enumerate(kw_rank, start=1)]
        out = []
        for nid, score in fused:
            node = by_id.get(nid)
            if node is None:
                continue
            node = dict(node)
            node["channel"] = channel
            node["rrf_score"] = round(score, 6)
            out.append(node)
            if len(out) >= max_results:
                break
        return out

    def _generate_snippet(self, content: str, keywords: list[str],
                          max_len: int = 200) -> str:
        """生成关键词上下文摘要"""
        content_lower = content.lower()
        for kw in keywords:
            pos = content_lower.find(kw)
            if pos != -1:
                start = max(0, pos - 80)
                end = min(len(content), pos + 120)
                snippet = content[start:end].strip()
                if start > 0:
                    snippet = "..." + snippet
                if end < len(content):
                    snippet = snippet + "..."
                return snippet[:max_len]
        return content[:max_len].strip()

    # ── 关联分析 ──

    def get_related(self, node_id: str, max_depth: int = 1) -> list[dict[str, Any]]:
        """获取关联节点"""
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT DISTINCT n.*, e.relation, e.weight
                FROM edges e
                JOIN nodes n ON (n.id = e.target_id OR n.id = e.source_id)
                WHERE (e.source_id = ? OR e.target_id = ?)
                AND n.id != ?
                ORDER BY e.weight DESC
                LIMIT 20
            """, (node_id, node_id, node_id)).fetchall()

            results = []
            for row in rows:
                node = dict(row)
                node["tags"] = json.loads(node.get("tags", "[]"))
                results.append(node)
            return results

    def create_edge(self, source_id: str, target_id: str,
                    relation: str = "related", weight: float = 1.0) -> bool:
        """创建节点关联"""
        try:
            with self._conn() as conn:
                conn.execute("""
                    INSERT INTO edges (source_id, target_id, relation, weight)
                    VALUES (?, ?, ?, ?)
                """, (source_id, target_id, relation, weight))
                conn.execute("UPDATE metadata SET value = (SELECT COUNT(*) FROM edges) WHERE key = 'edge_count'")
            return True
        except sqlite3.IntegrityError:
            return False

    # ── 同步到 Obsidian ──

    def sync_to_obsidian(self, vault_path: Path | None = None) -> dict[str, Any]:
        """同步节点到 Obsidian Markdown 文件"""
        target_dir = vault_path or OBSIDIAN_VAULT or OBSIDIAN_SYNC_DIR
        if not target_dir:
            logger.warning("未设置 Obsidian 同步目标目录")
            return {"synced": 0, "failed": 0, "errors": []}

        stats = {"synced": 0, "failed": 0, "errors": []}

        with self._conn() as conn:
            # 获取所有未同步或已更新的节点
            rows = conn.execute("""
                SELECT n.* FROM nodes n
                WHERE n.id NOT IN (
                    SELECT node_id FROM sync_log
                    WHERE direction = 'to_obsidian' AND status = 'success'
                    AND synced_at >= n.updated_at
                )
                ORDER BY n.updated_at DESC
                LIMIT 200
            """).fetchall()

            for row in rows:
                node = dict(row)
                node["tags"] = json.loads(node.get("tags", "[]"))
                try:
                    file_path = self._write_obsidian_file(target_dir, node)
                    conn.execute("""
                        INSERT INTO sync_log (node_id, direction, status, file_path)
                        VALUES (?, 'to_obsidian', 'success', ?)
                    """, (node["id"], str(file_path)))
                    stats["synced"] += 1
                except Exception as e:
                    conn.execute("""
                        INSERT INTO sync_log (node_id, direction, status, error_msg)
                        VALUES (?, 'to_obsidian', 'failed', ?)
                    """, (node["id"], str(e)))
                    stats["failed"] += 1
                    stats["errors"].append(str(e))

        if stats["synced"] > 0:
            logger.info(f"Obsidian 同步完成: {stats['synced']} 成功, {stats['failed']} 失败")
        return stats

    def _write_obsidian_file(self, base_dir: Path, node: dict[str, Any]) -> Path:
        """将节点写入 Obsidian Markdown 文件"""
        # 按类型分目录
        type_dir_map = {
            "statute": "statutes",
            "case": "cases",
            "benchmark": "benchmarks",
            "procedure": "procedures",
            "session": "sessions",
            "skill": "skills",
            "quality": "quality",
            "alert": "alerts",
        }
        subdir = type_dir_map.get(node["type"], "others")
        target_dir = base_dir / subdir
        target_dir.mkdir(parents=True, exist_ok=True)

        # 文件名（安全处理）
        safe_title = re.sub(r'[<>:"/\\|?*]', '_', node["title"])[:80]
        file_path = target_dir / f"{safe_title}.md"

        # 构建 frontmatter
        tags_yaml = "\n".join(f"  - {t}" for t in node["tags"])
        frontmatter = f"""---
id: {node['id']}
type: {node['type']}
score: {node['score']}
confidence: {node['confidence']}
tags:
{tags_yaml}
parent: {node['parent_id'] or ''}
source: {node['source']}
created: {node['created_at'][:10]}
updated: {node['updated_at'][:10]}
---

"""
        full_content = frontmatter + node["content"]
        file_path.write_text(full_content, encoding="utf-8")
        return file_path

    # ── 从 Obsidian 同步到 SQLite ──

    def sync_from_obsidian(self, obsidian_dir: Path | None = None) -> dict[str, Any]:
        """从 Obsidian Markdown 文件同步到 SQLite"""
        source_dir = obsidian_dir or OBSIDIAN_VAULT or OBSIDIAN_SYNC_DIR
        if not source_dir or not source_dir.exists():
            return {"synced": 0, "failed": 0, "errors": ["源目录不存在"]}

        stats = {"synced": 0, "failed": 0, "errors": []}

        for md_file in source_dir.rglob("*.md"):
            try:
                content = md_file.read_text(encoding="utf-8", errors="ignore")
                node = self._parse_obsidian_file(md_file, content)
                if node:
                    self._upsert_node_from_obsidian(node)
                    stats["synced"] += 1
            except Exception as e:
                stats["failed"] += 1
                stats["errors"].append(f"{md_file}: {e}")

        return stats

    def _parse_obsidian_file(self, file_path: Path, content: str) -> dict[str, Any] | None:
        """解析 Obsidian Markdown 文件"""
        if not content.startswith("---"):
            return None

        end = content.find("---", 3)
        if end == -1:
            return None

        yaml_text = content[3:end]
        body = content[end + 3:].strip()
        frontmatter = {}
        for line in yaml_text.strip().split("\n"):
            if ":" in line:
                key, _, value = line.partition(":")
                key = key.strip()
                value = value.strip().strip('"\'')
                if key == "tags":
                    continue  # 单独处理
                frontmatter[key] = value

        # 解析 tags
        tags = []
        in_tags = False
        for line in yaml_text.strip().split("\n"):
            if line.strip() == "tags:":
                in_tags = True
                continue
            if in_tags:
                if line.strip().startswith("- "):
                    tags.append(line.strip()[2:].strip().strip('"\''))
                else:
                    in_tags = False

        if not frontmatter.get("id"):
            return None

        node_id = frontmatter["id"]
        # 检查是否已有此 ID 的记录
        existing = self.get_node(node_id)
        if existing and existing["updated_at"] >= frontmatter.get("updated", ""):
            return None

        return {
            "id": node_id,
            "type": frontmatter.get("type", "statute"),
            "title": frontmatter.get("title", file_path.stem),
            "content": body,
            "score": float(frontmatter.get("score", 50)),
            "tags": tags,
            "parent_id": frontmatter.get("parent", "") or None,
            "source": frontmatter.get("source", "manual"),
            "confidence": frontmatter.get("confidence", "medium"),
        }

    def _upsert_node_from_obsidian(self, node: dict[str, Any]):
        """从解析的 Obsidian 节点更新或插入数据库"""
        tags_json = json.dumps(node["tags"], ensure_ascii=False)
        now = datetime.now().isoformat()

        with self._conn() as conn:
            existing = conn.execute(
                "SELECT id FROM nodes WHERE id = ?", (node["id"],)
            ).fetchone()

            if existing:
                conn.execute("""
                    UPDATE nodes SET title=?, content=?, score=?, tags=?,
                           confidence=?, updated_at=?
                    WHERE id=?
                """, (node["title"], node["content"], node["score"],
                      tags_json, node["confidence"], now, node["id"]))
            else:
                conn.execute("""
                    INSERT INTO nodes (id, type, title, content, score, tags,
                                       parent_id, source, confidence,
                                       created_at, updated_at, accessed_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (node["id"], node["type"], node["title"], node["content"],
                      node["score"], tags_json, node["parent_id"],
                      node["source"], node["confidence"], now, now, now))

            # 同步日志
            conn.execute("""
                INSERT INTO sync_log (node_id, direction, status)
                VALUES (?, 'to_sqlite', 'success')
            """, (node["id"],))

    # ── 评分与热度 ──

    def recalculate_scores(self):
        """重新计算所有节点评分"""
        now = datetime.now()
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT id, score, accessed_at, access_count,
                       (SELECT MAX(updated_at) FROM nodes) as max_updated
                FROM nodes
            """).fetchall()

            max_access = max((r["access_count"] for r in rows), default=1)
            for row in rows:
                # 时效因子（越新越高）
                days_since_update = (now - datetime.fromisoformat(
                    row["accessed_at"] or row["updated_at"])).days
                recency = max(0, 1 - days_since_update / 90)

                # 频率因子
                frequency = row["access_count"] / max_access

                # 新评分 = 原评分 * 0.5 + 时效 * 0.3 + 频率 * 0.2
                new_score = (
                    row["score"] * 0.5
                    + recency * 100 * 0.3
                    + frequency * 100 * 0.2
                )
                new_score = max(0, min(100, new_score))

                conn.execute(
                    "UPDATE nodes SET score = ? WHERE id = ?",
                    (new_score, row["id"])
                )

        logger.info("评分重算完成")

    def get_hot_nodes(self, limit: int = 50) -> list[dict[str, Any]]:
        """获取热点节点（高分 + 高频访问）"""
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT * FROM nodes
                ORDER BY score DESC, access_count DESC
                LIMIT ?
            """, (limit,)).fetchall()
            results = []
            for row in rows:
                node = dict(row)
                node["tags"] = json.loads(node.get("tags", "[]"))
                results.append(node)
            return results

    # ── 统计 ──

    def get_stats(self) -> dict[str, Any]:
        """获取 Memory Tree 统计信息"""
        with self._conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
            by_type = conn.execute("""
                SELECT type, COUNT(*) as cnt, AVG(score) as avg_score
                FROM nodes GROUP BY type
            """).fetchall()
            edges = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
            db_size = self.db_path.stat().st_size if self.db_path.exists() else 0

            return {
                "total_nodes": total,
                "total_edges": edges,
                "db_size_kb": db_size / 1024,
                "by_type": {r["type"]: {"count": r["cnt"], "avg_score": round(r["avg_score"], 1)}
                           for r in by_type},
            }

    # ── 工具 ──

    @staticmethod
    def _generate_id(type: str) -> str:
        """生成唯一节点 ID"""
        ts = int(time.time() * 1000)
        hash_input = f"{type}:{ts}:{os.urandom(4).hex()}"
        short_hash = hashlib.md5(hash_input.encode()).hexdigest()[:8]
        return f"node_{short_hash}"

    def export_all(self) -> list[dict[str, Any]]:
        """导出全部节点"""
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM nodes ORDER BY type, score DESC").fetchall()
            results = []
            for row in rows:
                node = dict(row)
                node["tags"] = json.loads(node.get("tags", "[]"))
                results.append(node)
            return results


# ===== 独立测试 =====
def test():
    """测试 Memory Tree 基本功能"""
    import tempfile
    db_path = Path(tempfile.mkdtemp()) / "test_memory.db"
    mt = MemoryTree(db_path)

    # 创建测试节点
    node1 = mt.create_node("statute", "大气污染防治法", "大气污染防治法内容摘要...",
                           tags=["env/air"], score=95.0, source="flowwiki")
    node2 = mt.create_node("case", "XX公司超标排放大气污染物案",
                           "某公司超标排放大气污染物被处罚...",
                           tags=["env/air", "enforcement/penalty"], score=80.0,
                           parent_id=node1["id"])

    print(f"节点数: {mt.get_stats()['total_nodes']}")
    print(f"节点1: {node1['id']} - {node1['title']} ({node1['score']}分)")
    print(f"节点2: {node2['id']} - {node2['title']} ({node2['score']}分)")

    # 测试检索
    results = mt.search("大气 超标")
    print(f"\n检索 '大气 超标': {len(results)} 条结果")
    for r in results:
        print(f"  [{r['score']:.0f}分] {r['title']}")

    # 测试关联
    related = mt.get_related(node1["id"])
    print(f"\n节点1 关联: {len(related)} 条")

    # 测试统计
    stats = mt.get_stats()
    print(f"\n统计: {json.dumps(stats, ensure_ascii=False, indent=2)}")

    # 清理
    mt.db_path = None  # 确保无连接残留
    import gc
    gc.collect()
    import shutil
    import time
    time.sleep(0.1)
    try:
        shutil.rmtree(db_path.parent)
    except PermissionError:
        print("(测试文件保留)")
    print("\n[OK] Memory Tree 测试通过")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test()
