#!/usr/bin/env python3
"""
workspace.py — 项目工作区（Phase B1）

以企业/项目为单位的持久化工作区：~/.eco/workspaces/<slug>/
  meta.json      元数据（名称/slug/创建/最近活跃/标签/关联纠错ID）
  notes.md       检查历史摘要、中间结论、关联法规（人类可读）
  history.jsonl  逐轮对话/事件记录（追加式）
  todos.md       待办事项

能力：
  - create/list/open/close/show（CLI 见 eco/commands/cmd_workspace.py）
  - chat 关联当前工作区后，工作区摘要经 prompt_engine 注入校验后进入动态层
  - 跨会话续接：detect_resume_intent() 识别"继续上次合力砖厂的检查"类意图并匹配工作区
  - freeze_to_memory_tree() 将摘要固化进 Memory Tree（复用 _scripts.memory_tree 接口）
"""

import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("workspace")

ECO_DIR = Path.home() / ".eco"
WS_ROOT = ECO_DIR / "workspaces"
ACTIVE_FILE = WS_ROOT / ".active"
WS_SOURCE_PREFIX = "workspace"  # prompt_engine 注入来源前缀

MAX_SUMMARY_LEN = 700  # 注入动态层的摘要长度上限（prompt_engine 单条上限 800）


def slugify(name: str) -> str:
    """企业/项目名 -> 安全目录 slug（保留中文，替换非法字符）"""
    s = re.sub(r"[\\/:*?\"<>|\s]+", "-", name.strip())
    s = s.strip("-._")
    return s or f"ws-{int(time.time())}"


class Workspace:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.meta_path = self.path / "meta.json"
        self.notes_path = self.path / "notes.md"
        self.history_path = self.path / "history.jsonl"
        self.todos_path = self.path / "todos.md"

    # ── 元数据 ──
    @property
    def meta(self) -> dict:
        if not self.meta_path.exists():
            return {}
        try:
            return json.loads(self.meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_meta(self, meta: dict):
        meta["updated_at"] = datetime.now().isoformat(timespec="seconds")
        self.meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                                  encoding="utf-8")

    def touch(self):
        m = self.meta
        if m:
            self._save_meta(m)

    # ── 历史/事件 ──
    def add_event(self, kind: str, content: str, **extra):
        """追加一条事件到 history.jsonl（kind: user/assistant/note/law/todo/correction ...）"""
        rec = {"ts": datetime.now().isoformat(timespec="seconds"),
               "kind": kind, "content": content}
        rec.update(extra)
        with self.history_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def history(self, limit: int = 0) -> list[dict]:
        if not self.history_path.exists():
            return []
        out = []
        with self.history_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return out[-limit:] if limit else out

    # ── 笔记/待办 ──
    def append_note(self, text: str):
        with self.notes_path.open("a", encoding="utf-8") as f:
            f.write(f"\n- [{datetime.now().isoformat(timespec='seconds')}] {text}\n")

    def append_todo(self, text: str):
        with self.todos_path.open("a", encoding="utf-8") as f:
            f.write(f"- [ ] {text}\n")

    def notes(self) -> str:
        return self.notes_path.read_text(encoding="utf-8") if self.notes_path.exists() else ""

    def todos(self) -> str:
        return self.todos_path.read_text(encoding="utf-8") if self.todos_path.exists() else ""

    # ── 摘要（注入动态层用）──
    def summary(self, max_len: int = MAX_SUMMARY_LEN) -> str:
        """工作区摘要：名称 + 最近历史摘要 + 关联法规 + 待办 + 纠错引用"""
        m = self.meta
        parts = [f"当前工作区：{m.get('name', self.path.name)}（{m.get('category', '执法检查')}）"]
        events = self.history()
        convs = [e for e in events if e.get("kind") in ("user", "assistant")]
        if convs:
            parts.append(f"历史对话 {len(convs)} 轮片段：")
            for e in convs[-6:]:
                tag = "问" if e["kind"] == "user" else "答"
                parts.append(f"  [{tag}] {e.get('content', '')[:120]}")
        laws = [e.get("content", "") for e in events if e.get("kind") == "law"]
        if laws:
            parts.append("关联法规：" + "；".join(dict.fromkeys(laws[-8:])))
        todos = [l for l in self.todos().splitlines() if l.strip().startswith("- [ ]")]
        if todos:
            parts.append("待办事项：" + "；".join(t.replace("- [ ]", "").strip() for t in todos[-5:]))
        corr = m.get("correction_refs") or []
        if corr:
            parts.append("关联纠错：" + "；".join(str(c)[:60] for c in corr[-5:]))
        text = "\n".join(parts)
        return text[:max_len]


class WorkspaceManager:
    """工作区管理器"""

    def __init__(self, root: Path = None):
        self.root = Path(root) if root else WS_ROOT
        self.root.mkdir(parents=True, exist_ok=True)
        self.active_file = self.root / ".active"

    def _path(self, slug: str) -> Path:
        return self.root / slug

    def create(self, name: str, category: str = "执法检查", tags: list[str] | None = None) -> Workspace:
        slug = slugify(name)
        path = self._path(slug)
        if path.exists():
            raise FileExistsError(f"工作区已存在: {slug}")
        path.mkdir(parents=True)
        ws = Workspace(path)
        meta = {
            "name": name, "slug": slug, "category": category,
            "tags": tags or [],
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "correction_refs": [],
        }
        ws.meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        ws.notes_path.write_text(f"# {name}\n\n## 检查历史摘要与中间结论\n", encoding="utf-8")
        ws.todos_path.write_text(f"# {name} 待办事项\n", encoding="utf-8")
        ws.history_path.touch()
        logger.info(f"[Workspace] created: {slug}")
        return ws

    def list(self) -> list[dict]:
        out = []
        for p in sorted(self.root.iterdir()):
            if p.is_dir() and not p.name.startswith("."):
                ws = Workspace(p)
                m = ws.meta
                if m:
                    m["n_events"] = len(ws.history())
                    out.append(m)
        return out

    def get(self, name_or_slug: str) -> Workspace | None:
        p = self._path(name_or_slug)
        if p.is_dir():
            return Workspace(p)
        slug = slugify(name_or_slug)
        p = self._path(slug)
        if p.is_dir():
            return Workspace(p)
        # 模糊匹配名称
        for m in self.list():
            if m.get("name") == name_or_slug:
                return Workspace(self._path(m["slug"]))
        return None

    def open(self, name_or_slug: str) -> Workspace | None:
        ws = self.get(name_or_slug)
        if ws:
            self.active_file.write_text(ws.meta.get("slug", ws.path.name), encoding="utf-8")
            ws.touch()
            logger.info(f"[Workspace] opened: {ws.path.name}")
        return ws

    def close(self) -> str | None:
        cur = self.current_name()
        if self.active_file.exists():
            self.active_file.unlink()
        return cur

    def current_name(self) -> str | None:
        if self.active_file.exists():
            s = self.active_file.read_text(encoding="utf-8").strip()
            return s or None
        return None

    def current(self) -> Workspace | None:
        s = self.current_name()
        if not s:
            return None
        p = self._path(s)
        return Workspace(p) if p.is_dir() else None

    # ── 跨会话续接意图识别 ──
    _RESUME_RE = re.compile(r"继续|接着|恢复|接着上次|上次|续接|continue", re.IGNORECASE)

    def detect_resume_intent(self, text: str) -> Workspace | None:
        """识别"继续上次合力砖厂的检查"类意图，匹配并返回工作区（不打开）"""
        t = (text or "").strip()
        if not t or not self._RESUME_RE.search(t):
            return None
        cands = self.list()
        if not cands:
            return None
        # 1) 名字命中：题干包含工作区名（或反之）
        for m in cands:
            name = m.get("name", "")
            if name and (name in t or (len(name) >= 4 and t.find(name[:4]) >= 0)):
                return Workspace(self._path(m["slug"]))
        # 2) "上次/继续"无明确名称：取最近活跃
        cands.sort(key=lambda m: m.get("updated_at", ""), reverse=True)
        return Workspace(self._path(cands[0]["slug"]))

    # ── 提示词动态层注入 ──
    def inject_current_summary(self, engine=None, task_id: str = "") -> bool:
        """将当前工作区摘要经 prompt_engine 校验后注入动态层"""
        ws = self.current()
        if ws is None:
            return False
        if engine is None:
            from agent_core.prompt_engine import get_prompt_engine
            engine = get_prompt_engine()
        engine.clear_injections(source_prefix=WS_SOURCE_PREFIX)
        return engine.inject(ws.summary(), source=f"{WS_SOURCE_PREFIX}:{ws.meta.get('slug', '')}",
                             task_id=task_id)

    def clear_injection(self, engine=None):
        if engine is None:
            from agent_core.prompt_engine import get_prompt_engine
            engine = get_prompt_engine()
        engine.clear_injections(source_prefix=WS_SOURCE_PREFIX)

    # ── 固化进 Memory Tree ──
    def freeze_to_memory_tree(self, ws: Workspace, db_path: Path = None) -> dict:
        """将工作区摘要固化进 Memory Tree（复用现有记忆接口）"""
        try:
            from _scripts.memory_tree import MemoryTree
        except ImportError:
            return {"ok": False, "error": "memory_tree 模块不可用"}
        m = ws.meta
        try:
            mt = MemoryTree(db_path=db_path)
            node = mt.create_node(
                type="case",  # Memory Tree 节点类型受 schema 约束，工作区固化归入 case
                title=f"工作区-{m.get('name', ws.path.name)}",
                content=ws.summary(max_len=2000),
                tags=["workspace", m.get("category", "执法检查")] + list(m.get("tags", [])),
            )
            ws.add_event("note", "工作区摘要已固化进 Memory Tree")
            return {"ok": True, "node": node if isinstance(node, dict) else str(node)}
        except Exception as e:
            logger.warning(f"[Workspace] freeze_to_memory_tree 失败: {e}")
            return {"ok": False, "error": str(e)}


_manager: WorkspaceManager | None = None


def get_workspace_manager() -> WorkspaceManager:
    global _manager
    if _manager is None:
        _manager = WorkspaceManager()
    return _manager


def _reset_for_test():
    global _manager
    _manager = None
