#!/usr/bin/env python3
"""
checkpoint.py — 会话检查点/回滚（对标 Claude Code checkpoint+rewind / Hermes /undo）

每轮用户输入前自动快照，存 ~/.eco/checkpoints/<session>/：
  <NNNN>.json  {id, ts, history, decisions_count, workspace: {slug, files}}

快照内容：
  - history          会话历史（REPL 内存中的 user/assistant 消息列表）
  - decisions_count  ~/.eco/decisions.jsonl 当前行数（SM3 决策链只追加不回滚，记数用于展示）
  - workspace.files  当前工作区文件清单 + sha256 + 内容（notes.md/todos.md/history.jsonl 等）

能力：
  create(history, ws=None)  快照
  list()                    列举检查点
  rewind(n)                 恢复到第 n 个检查点（返回快照 dict，并按快照还原 workspace 文件；
                            调用方用返回的 history 截断内存会话历史）

损坏快照容错：单文件 JSON 损坏只跳过该检查点，不影响其它。
"""
import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("checkpoint")

ECO_DIR = Path.home() / ".eco"
CP_ROOT = ECO_DIR / "checkpoints"
DECISIONS_FILE = ECO_DIR / "decisions.jsonl"

# 纳入快照的工作区文件（存在才收）
_WS_SNAPSHOT_FILES = ("meta.json", "notes.md", "todos.md", "history.jsonl")

_MAX_CP_PER_SESSION = 50  # 每会话检查点上限，超出滚动淘汰最旧


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _decisions_count(path: Path = None) -> int:
    p = path or DECISIONS_FILE
    try:
        if p.exists():
            with p.open("r", encoding="utf-8") as f:
                return sum(1 for line in f if line.strip())
    except OSError:
        pass
    return 0


def _snapshot_workspace_files(ws_path: Path) -> dict:
    """工作区文件清单：相对路径 -> {sha256, size, content(utf-8)}"""
    files = {}
    for name in _WS_SNAPSHOT_FILES:
        fp = ws_path / name
        if not fp.is_file():
            continue
        try:
            data = fp.read_bytes()
            files[name] = {
                "sha256": _sha256(data),
                "size": len(data),
                "content": data.decode("utf-8", errors="replace"),
            }
        except OSError:
            continue
    return files


def _restore_workspace_files(ws_path: Path, files: dict) -> list[str]:
    """按快照还原工作区文件；删除快照外的受管文件（回滚后新增的）。"""
    restored = []
    for name, info in files.items():
        fp = ws_path / name
        try:
            fp.write_text(info.get("content", ""), encoding="utf-8")
            restored.append(name)
        except OSError as e:
            logger.warning(f"[Checkpoint] 还原失败 {fp}: {e}")
    # 快照时不在清单里的受管文件（回滚后多余）删除
    for name in _WS_SNAPSHOT_FILES:
        if name not in files:
            fp = ws_path / name
            if fp.is_file():
                try:
                    fp.unlink()
                except OSError:
                    pass
    return restored


class CheckpointStore:
    """按会话隔离的检查点存储。"""

    def __init__(self, session: str = "default", root: Path = None):
        self.session = session or "default"
        base = Path(root) if root else CP_ROOT
        self.dir = base / self.session
        self.dir.mkdir(parents=True, exist_ok=True)

    # ── 内部 ──
    def _cp_path(self, n: int) -> Path:
        return self.dir / f"{n:04d}.json"

    def _next_id(self) -> int:
        ids = [c["id"] for c in self.list()]
        return (max(ids) + 1) if ids else 1

    def _load(self, path: Path) -> dict | None:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"[Checkpoint] 跳过损坏快照 {path.name}: {e}")
            return None

    def _evict(self):
        cps = self.list()
        while len(cps) > _MAX_CP_PER_SESSION:
            victim = cps.pop(0)
            try:
                self._cp_path(victim["id"]).unlink()
            except OSError:
                pass

    # ── 能力 ──
    def create(self, history: list | None = None, ws=None,
               decisions_file: Path = None) -> dict:
        """创建检查点：会话历史 + decisions 计数 + 工作区文件快照"""
        n = self._next_id()
        ws_info = {"slug": "", "files": {}}
        if ws is not None:
            ws_info = {
                "slug": ws.meta.get("slug", ws.path.name) if hasattr(ws, "meta") else ws.path.name,
                "files": _snapshot_workspace_files(ws.path),
            }
        cp = {
            "id": n,
            "session": self.session,
            "ts": datetime.now().isoformat(timespec="seconds"),
            "history": list(history or []),
            "decisions_count": _decisions_count(decisions_file),
            "workspace": ws_info,
        }
        self._cp_path(n).write_text(json.dumps(cp, ensure_ascii=False, indent=2),
                                    encoding="utf-8")
        self._evict()
        return cp

    def list(self) -> list[dict]:
        """列举检查点（按 id 升序；损坏快照跳过）"""
        out = []
        for p in sorted(self.dir.glob("*.json")):
            cp = self._load(p)
            if cp is not None and isinstance(cp.get("id"), int):
                out.append(cp)
        out.sort(key=lambda c: c["id"])
        return out

    def get(self, n: int) -> dict | None:
        p = self._cp_path(n)
        if not p.is_file():
            return None
        return self._load(p)

    def rewind(self, n: int, ws=None) -> dict | None:
        """恢复到第 n 个检查点：
        - 若提供 ws，按快照还原 workspace 文件
        - 删除 n 之后的检查点（回滚后新时间线）
        - 返回检查点 dict（调用方取 cp["history"] 截断内存历史）；失败返回 None"""
        cp = self.get(n)
        if cp is None:
            return None
        if ws is not None:
            _restore_workspace_files(ws.path, cp.get("workspace", {}).get("files", {}))
        for later in self.list():
            if later["id"] > n:
                try:
                    self._cp_path(later["id"]).unlink()
                except OSError:
                    pass
        return cp
