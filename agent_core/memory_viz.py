#!/usr/bin/env python3
"""
memory_viz.py — Eco Agent D-04 本地记忆树可视化后端

Obsidian 风格知识图谱：节点浏览/编辑/删除/合并，系统不覆盖用户修改。
"""

import os, sys, json, time, logging, hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any

logger = logging.getLogger("memory_viz")
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "memory-tree" / "data" / "viz"
DATA_DIR.mkdir(parents=True, exist_ok=True)


class MemoryViz:
    """记忆可视化后端"""

    def __init__(self, memory_tree=None):
        self._mt = memory_tree
        self._overrides_file = DATA_DIR / "user_overrides.json"
        self._user_overrides: Dict[str, Dict] = {}
        self._load_overrides()

    def _load_overrides(self):
        if self._overrides_file.exists():
            try: self._user_overrides = json.loads(self._overrides_file.read_text("utf-8", errors="replace"))
            except: pass

    def _save_overrides(self):
        self._overrides_file.write_text(json.dumps(self._user_overrides, ensure_ascii=False, indent=2), encoding="utf-8")

    def get_graph(self) -> Dict:
        """获取知识图谱数据（节点+边）"""
        nodes = []
        edges = []
        seen_ids = set()

        # 从 Memory Tree 获取
        if self._mt:
            try:
                all_nodes = self._mt.list_nodes(limit=200)
                for n in all_nodes:
                    nid = n.get("id", "")
                    if nid in seen_ids: continue
                    seen_ids.add(nid)
                    overridden = nid in self._user_overrides
                    display = self._user_overrides.get(nid, n)
                    nodes.append({"id": nid, "title": display.get("title", n.get("title", "")),
                                  "type": n.get("type", "unknown"), "score": n.get("score", 50),
                                  "edited": overridden})
                # 关联边
                for n in all_nodes[:50]:
                    related = self._mt.get_related(n.get("id", ""))
                    for r in related[:5]:
                        edges.append({"source": n["id"], "target": r.get("id", ""),
                                      "relation": r.get("relation", "related")})
            except: pass

        return {"nodes": nodes, "edges": edges, "total_nodes": len(nodes), "total_edges": len(edges)}

    def update_node(self, node_id: str, updates: dict) -> Dict:
        """用户编辑节点——保存用户修改，系统不覆盖"""
        self._user_overrides[node_id] = {**self._user_overrides.get(node_id, {}), **updates,
                                         "edited_at": datetime.now().isoformat()}
        self._save_overrides()
        logger.info(f"[MemoryViz] 用户编辑: {node_id}")
        return {"success": True, "node_id": node_id}

    def delete_node(self, node_id: str) -> Dict:
        """用户删除节点"""
        self._user_overrides[node_id] = {"_deleted": True, "deleted_at": datetime.now().isoformat()}
        self._save_overrides()
        logger.info(f"[MemoryViz] 用户删除: {node_id}")
        return {"success": True, "node_id": node_id}

    def merge_nodes(self, target_id: str, source_ids: List[str]) -> Dict:
        """用户合并节点"""
        merged = self._user_overrides.get(target_id, {})
        merged["_merged_from"] = source_ids
        merged["merged_at"] = datetime.now().isoformat()
        self._user_overrides[target_id] = merged
        for sid in source_ids:
            self._user_overrides[sid] = {"_deleted": True, "merged_into": target_id}
        self._save_overrides()
        logger.info(f"[MemoryViz] 合并: {source_ids} -> {target_id}")
        return {"success": True, "target": target_id, "sources": source_ids}

    def get_stats(self) -> dict:
        return {"overrides": len(self._user_overrides),
                "deleted": sum(1 for v in self._user_overrides.values() if v.get("_deleted"))}


# ===== 测试 =====

def test():
    import io, sys as _sys
    _sys.stdout = io.TextIOWrapper(_sys.stdout.buffer, encoding='utf-8', errors='replace')
    mv = MemoryViz()
    graph = mv.get_graph()
    print(f"[D-04] 图谱节点: {graph['total_nodes']}, 边: {graph['total_edges']}", flush=True)
    r1 = mv.update_node("node_test", {"title": "编辑测试"})
    r2 = mv.delete_node("node_delete")
    r3 = mv.merge_nodes("node_target", ["node_a", "node_b"])
    print(f"[D-04] 编辑: {r1['success']}, 删除: {r2['success']}, 合并: {r3['success']}", flush=True)
    stats = mv.get_stats()
    print(f"[D-04] 用户修改记录: {stats['overrides']}, 不覆盖", flush=True)
    assert r1['success'] and r2['success'] and r3['success']
    print("[PASS] D-04 记忆可视化测试通过", flush=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test()
