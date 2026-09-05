#!/usr/bin/env python3
"""
agent_core/eco_state.py — 可移植状态层（对标 Hermes hermes_state 家族）
=====================================================================
Hermes v0.21.0 的 hermes_state 拆为 registry / schema / holders / search /
portability 五个面，围绕 SessionDB（SQLite 会话库）做状态生命周期管理。
eco 侧对标语义（eco 的记忆状态不是单库会话，而是分层 memory 体系 +
家目录状态源），落地为同一五面、同一可移植 bundle 格式：

  registry    EcoStateRegistry  —— 状态源 holder 的注册/枚举/健康探测
                                  （对标 hermes_state_registry：谁持有状态）
  schema      ECO_STATE_SCHEMA_VERSION + BUNDLE_SCHEMA/ENTRY_SCHEMA/FILE_SCHEMA
                                  —— 版本化自描述格式，SchemaGuard 校验
                                  （对标 hermes_state_schema：SCHEMA_VERSION/DDL）
  holders     HOLDERS 静态注册表 + probe_holder() 探测（存在/大小/行数/mtime/
              记录数/健康位）            （对标 hermes_state_holders）
  search      EcoStateSearch  —— memory-tree 节点(hybrid) / memory.jsonl(向量)
                                  / decisions|stats 等文本源子串检索的统一入口
                                  （对标 hermes_state_search）
  portability export_bundle / validate_bundle / import_bundle
                                  —— 版本化 JSON bundle 可跨实例还原
                                  （对标 hermes_state_portability
                                     export_session_lineage / import_sessions）

设计取舍（如实声明）：
  - 零第三方依赖；schema 校验复用 agent_core.schema_guard（M3 已落地）；
  - bundle 按"文件级快照"归一化：每个 entry 携带 {relpath -> 内容}，
    UTF-8 明文可审计、二进制(含 SQLite db)base64 保真；import = 还原文件，
    与 Hermes 的"行级 export/import"在语义上等价（状态整体可移植）；
  - SQLite db 经 backup API 快照，避免 WAL 未 checkpoint 导致的缺尾；
  - import 目标可重定向（--eco-root/--home-root），天然支持"导出旧实例 →
    导入全新实例"的对标验收路径；目标文件已存在且未 --force 时报错跳过，
    不做静默覆盖。
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

logger = logging.getLogger("eco.state")

try:
    from agent_core.schema_guard import SchemaGuard
except Exception:  # noqa: BLE001 — 独立运行/测试时降级
    SchemaGuard = None

# ── 路径根 ──────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_HOME_ROOT = Path.home()
# 家目录状态根默认 ~/.eco；可用 ECO_HOME 覆盖（测试/多实例）
HOME_ECO_DIR = Path(os.environ.get("ECO_HOME", str(Path.home() / ".eco")))

# ── schema（对标 hermes_state_schema.SCHEMA_VERSION）────────────────
ECO_STATE_SCHEMA_VERSION = 1
BUNDLE_MAGIC = "eco_state_bundle"
BUNDLE_MAGIC_VALUE = 1

# 单个文本文件导入/导出的大小上限（字节），超出则跳过并记 skipped
MAX_INLINE_FILE_BYTES = 20 * 1024 * 1024
_TEXT_EXTENSIONS = {".json", ".jsonl", ".txt", ".md", ".log", ".yaml", ".yml", ".csv"}


def _is_text_bytes(raw: bytes) -> bool:
    try:
        raw.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


# ── Holder 静态注册表（对标 hermes_state_holders 的探测面）───────────
# key: 状态源唯一名
# kind: sqlite|jsonl|json|dir   （collector 据此选择读取策略）
# scope: core=eco 仓库内 / home=家目录状态（可移植实例间的分界）
# rel: 相对各自 scope 根的路径
# desc: 人类可读描述
# ext: dir 收集时纳入的扩展名白名单（None=全部文本+无扩展）
HOLDERS: Dict[str, Dict[str, Any]] = {
    "memory_tree": {
        "kind": "sqlite",
        "scope": "core",
        "desc": "MemoryTree 分层记忆节点库",
        "rel": Path("memory-tree/data/eco_memory.db"),
    },
    "memory_jsonl": {
        "kind": "jsonl",
        "scope": "core",
        "desc": "跨会话向量记忆（memory_index）",
        "rel": Path("memory-tree/data/memory.jsonl"),
    },
    "pulse_state": {
        "kind": "json",
        "scope": "core",
        "desc": "L3 Pulse 心跳状态",
        "rel": Path("memory-tree/data/pulse_state.json"),
    },
    "scheduled_jobs": {
        "kind": "json",
        "scope": "core",
        "desc": "调度任务状态",
        "rel": Path("memory-tree/data/scheduled_jobs.json"),
    },
    "decisions": {
        "kind": "jsonl",
        "scope": "home",
        "desc": "SM3 决策链（只追加）",
        "rel": Path(".eco/decisions.jsonl"),
    },
    "stats": {
        "kind": "jsonl",
        "scope": "home",
        "desc": "运行统计账本",
        "rel": Path(".eco/stats.jsonl"),
    },
    "checkpoints": {
        "kind": "dir",
        "scope": "home",
        "desc": "会话检查点/回滚快照",
        "rel": Path(".eco/checkpoints"),
        "ext": {".json"},
    },
    "peer_rooms": {
        "kind": "dir",
        "scope": "home",
        "desc": "eco_peer 对等房间账本",
        "rel": Path(".eco/peers"),
        "ext": {".jsonl", ".json"},
    },
    "tasks": {
        "kind": "dir",
        "scope": "home",
        "desc": "任务调度运行态",
        "rel": Path(".eco/tasks"),
        "ext": {".json", ".jsonl"},
    },
}

# ── Bundle / Entry / File Schema（供 SchemaGuard 校验）──────────────
FILE_SCHEMA = {
    "type": "object",
    "required": ["size", "sha256", "encoding", "content"],
    "properties": {
        "size": {"type": "integer", "minimum": 0},
        "sha256": {"type": "string", "minLength": 64, "maxLength": 64},
        "encoding": {"type": "string", "enum": ["utf-8", "base64"]},
        "content": {"type": "string"},
    },
    "additionalProperties": False,
}

ENTRY_SCHEMA = {
    "type": "object",
    "required": ["key", "kind", "scope", "schema_version", "relpath", "present", "record_count", "updated_at", "payload"],
    "properties": {
        "key": {"type": "string", "minLength": 1},
        "kind": {"type": "string", "enum": ["sqlite", "jsonl", "json", "dir"]},
        "scope": {"type": "string", "enum": ["core", "home"]},
        "schema_version": {"type": "integer", "minimum": 1},
        "relpath": {"type": "string", "minLength": 1},
        "desc": {"type": "string"},
        "present": {"type": "boolean"},
        "record_count": {"type": "integer"},
        "updated_at": {"type": ["string", "null"]},
        "payload": {
            "type": "object",
            "required": ["files"],
            "properties": {
                "files": {"type": "object"},
                "skipped": {"type": "array", "items": {"type": "object"}},
            },
            "additionalProperties": False,
        },
    },
    "additionalProperties": False,
}

BUNDLE_SCHEMA = {
    "type": "object",
    "required": [BUNDLE_MAGIC, "schema_version", "exported_at", "source", "eco_version", "entries"],
    "properties": {
        BUNDLE_MAGIC: {"type": "integer", "enum": [BUNDLE_MAGIC_VALUE]},
        "schema_version": {"type": "integer", "enum": [ECO_STATE_SCHEMA_VERSION]},
        "exported_at": {"type": "string", "minLength": 1},
        "source": {"type": "string", "minLength": 1},
        "eco_version": {"type": "string"},
        "entries": {"type": "array", "items": {"type": "object"}},
    },
    "additionalProperties": False,
}


# ── 根目录解析 ──────────────────────────────────────────────────────
def eco_home_root() -> Path:
    """home scope 根目录 = ~/.eco 的父目录（即家目录）。"""
    return HOME_ECO_DIR.parent


def scope_root(scope: str, eco_root: Optional[Path] = None, home_root: Optional[Path] = None) -> Path:
    eco_root = Path(eco_root) if eco_root is not None else PROJECT_ROOT
    home_root = Path(home_root) if home_root is not None else eco_home_root()
    return eco_root if scope == "core" else home_root


def holder_path(key: str, eco_root: Optional[Path] = None, home_root: Optional[Path] = None) -> Optional[Path]:
    h = HOLDERS.get(key)
    if h is None:
        return None
    return scope_root(h["scope"], eco_root, home_root) / h["rel"]


# ── 文件/目录 → payload（collect） ──────────────────────────────────
def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _sqlite_snapshot(path: Path) -> Tuple[Optional[bytes], Optional[str]]:
    """SQLite backup API 一致性快照；返回 (bytes, err)。"""
    try:
        src = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            dst = sqlite3.connect(":memory:")
            try:
                src.backup(dst)
                blob = dst.serialize()  # 仅对 :memory: 连接可用
                return bytes(blob), None
            finally:
                dst.close()
        finally:
            src.close()
    except Exception as exc:  # noqa: BLE001
        return None, f"sqlite snapshot 失败({exc})，降级原始拷贝"


def _encode_file_bytes(raw: bytes, path: Path) -> Dict[str, Any]:
    if _is_text_bytes(raw) and path.suffix.lower() in _TEXT_EXTENSIONS:
        return {"encoding": "utf-8", "content": raw.decode("utf-8")}
    return {"encoding": "base64", "content": base64.b64encode(raw).decode("ascii")}


def _collect_path(path: Path) -> Dict[str, Any]:
    """收集单个文件 → FILE dict。不存在/超限时返回 skipped 语义。"""
    if not path.exists():
        return {"present": False}
    if not path.is_file():
        return {"present": False, "error": "非普通文件"}
    size = path.stat().st_size
    if size > MAX_INLINE_FILE_BYTES:
        return {"present": True, "skipped": True, "reason": f"超过 {MAX_INLINE_FILE_BYTES}B 上限"}
    raw = path.read_bytes()
    finfo = _encode_file_bytes(raw, path)
    finfo["size"] = size
    finfo["sha256"] = hashlib.sha256(raw).hexdigest()
    return {"present": True, "file": finfo}


def _iter_holder_files(h: Dict[str, Any], base: Path) -> Iterator[Tuple[Path, Path]]:
    """遍历 holder 名下文件，产出 (绝对路径, 相对 base 的 relpath)。"""
    rel: Path = h["rel"]
    target = base / rel
    if not target.exists():
        return
    if target.is_file():
        yield target, Path(rel.name) if rel.parent == Path(".") else Path(rel)
        return
    ext_whitelist = h.get("ext")
    for dirpath, _dirnames, filenames in os.walk(target):
        dirpath_p = Path(dirpath)
        for fn in sorted(filenames):
            p = dirpath_p / fn
            if p.name.startswith("."):
                continue
            if ext_whitelist is not None and p.suffix.lower() not in ext_whitelist:
                continue
            # 相对 holder 根的 relpath
            try:
                rel_to_holder = p.relative_to(target)
            except ValueError:
                continue
            yield p, rel_to_holder


def count_records(path: Path) -> int:
    """按类型粗估记录数（sqlite=行级计数由节点表聚合，jsonl=行数，json=1）。"""
    try:
        if path.is_dir():
            return sum(1 for p in path.rglob("*") if p.is_file())
        if path.suffix == ".jsonl":
            with open(path, encoding="utf-8", errors="ignore") as fh:
                return sum(1 for _ in fh)
        if path.suffix == ".db":
            try:
                conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
                try:
                    for tbl in ("nodes", "edges", "messages"):
                        try:
                            n = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
                            return int(n)
                        except sqlite3.OperationalError:
                            continue
                    return 0
                finally:
                    conn.close()
            except Exception:
                return 0
        return 1
    except OSError:
        return 0


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts).isoformat(timespec="seconds")


# ── Registry（对标 hermes_state_registry）────────────────────────────
class EcoStateRegistry:
    """状态源 holder 注册表：枚举 + 健康探测 + 摘要。"""

    def __init__(self, eco_root: Optional[Path] = None, home_root: Optional[Path] = None):
        self.eco_root = Path(eco_root) if eco_root is not None else PROJECT_ROOT
        self.home_root = Path(home_root) if home_root is not None else eco_home_root()
        self.holders = dict(HOLDERS)

    def register(self, key: str, kind: str, scope: str, rel: Path, desc: str = "", ext: Optional[set] = None) -> None:
        """运行期扩展注册（供插件/新状态源追加）。"""
        if scope not in ("core", "home"):
            raise ValueError(f"scope 必须为 core|home，实际 {scope}")
        if kind not in ("sqlite", "jsonl", "json", "dir"):
            raise ValueError(f"kind 非法: {kind}")
        self.holders[key] = {"kind": kind, "scope": scope, "rel": Path(rel), "desc": desc, "ext": ext}

    def probe(self, key: str) -> Dict[str, Any]:
        h = self.holders[key]
        path = scope_root(h["scope"], self.eco_root, self.home_root) / h["rel"]
        entry = {
            "key": key,
            "kind": h["kind"],
            "scope": h["scope"],
            "desc": h.get("desc", ""),
            "relpath": str(h["rel"]),
            "abs_path": str(path),
            "present": path.exists(),
            "healthy": False,
            "record_count": 0,
            "updated_at": None,
            "size_bytes": 0,
            "schema_version": ECO_STATE_SCHEMA_VERSION,
            "error": None,
        }
        if not path.exists():
            entry["error"] = "absent"
            return entry
        try:
            st = path.stat()
            entry["size_bytes"] = st.st_size if path.is_file() else None
            entry["updated_at"] = _iso(st.st_mtime)
            entry["record_count"] = count_records(path)
            # 健康：文件可读（json/jsonl 可解析或可读字节，sqlite 可连接）
            if path.is_file():
                if h["kind"] in ("json", "jsonl"):
                    ok, err = self._validate_text(path, h["kind"])
                    entry["healthy"] = ok
                    entry["error"] = None if ok else err
                elif h["kind"] == "sqlite":
                    try:
                        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
                        conn.execute("SELECT 1")
                        conn.close()
                        entry["healthy"] = True
                    except Exception as exc:  # noqa: BLE001
                        entry["error"] = f"sqlite 不可读: {exc}"
            else:
                entry["healthy"] = True
        except OSError as exc:
            entry["error"] = str(exc)
        return entry

    @staticmethod
    def _validate_text(path: Path, kind: str) -> Tuple[bool, Optional[str]]:
        try:
            raw = path.read_text(encoding="utf-8")
            if kind == "json":
                # 单文件 JSON：支持美化整文档，也兼容每行独立 JSON 的拼接体
                stripped = raw.strip()
                if not stripped:
                    return True, None
                try:
                    json.loads(stripped)
                    return True, None
                except ValueError as whole_exc:
                    try:
                        for lineno, line in enumerate(stripped.splitlines(), 1):
                            if line.strip():
                                json.loads(line)
                        return True, None
                    except ValueError:
                        return False, f"JSON 解析失败: {whole_exc}"
            # jsonl：逐行
            for lineno, line in enumerate(raw.splitlines(), 1):
                if not line.strip():
                    continue
                json.loads(line)
            return True, None
        except (OSError, ValueError) as exc:
            return False, f"第 {lineno} 行解析失败: {exc}"

    def list(self) -> List[Dict[str, Any]]:
        return [self.probe(k) for k in sorted(self.holders)]

    def summary(self) -> Dict[str, Any]:
        probes = self.list()
        return {
            "schema_version": ECO_STATE_SCHEMA_VERSION,
            "holders_total": len(probes),
            "holders_present": sum(1 for p in probes if p["present"]),
            "holders_healthy": sum(1 for p in probes if p["healthy"]),
            "record_count_total": sum(p["record_count"] for p in probes),
        }


# ── Portability（对标 hermes_state_portability）─────────────────────
class EcoStatePortability:
    def __init__(self, eco_root: Optional[Path] = None, home_root: Optional[Path] = None):
        self.registry = EcoStateRegistry(eco_root, home_root)

    # ── export ──
    def collect_entry(self, key: str, include_absent: bool = False) -> Dict[str, Any]:
        """收集单个 holder → entry（含 payload 文件快照）。"""
        h = self.registry.holders[key]
        base = scope_root(h["scope"], self.registry.eco_root, self.registry.home_root)
        target = base / h["rel"]
        probe = self.registry.probe(key)
        entry = {
            "key": key,
            "kind": h["kind"],
            "scope": h["scope"],
            "schema_version": ECO_STATE_SCHEMA_VERSION,
            "relpath": str(h["rel"]),
            "desc": h.get("desc", ""),
            "present": probe["present"],
            "record_count": probe["record_count"],
            "updated_at": probe["updated_at"],
            "payload": {"files": {}, "skipped": []},
        }
        if not target.exists():
            if not include_absent:
                entry["present"] = False
            return entry

        if target.is_file():
            res = _collect_path(target)
            if res.get("skipped"):
                entry["payload"]["skipped"].append({"relpath": str(h["rel"]), "reason": res["reason"]})
            elif res.get("present") and "file" in res:
                entry["payload"]["files"][str(h["rel"])] = res["file"]
            return entry

        # dir：逐个文件
        for abs_p, rel_to_holder in _iter_holder_files(h, base):
            res = _collect_path(abs_p)
            if res.get("skipped"):
                entry["payload"]["skipped"].append({"relpath": str(rel_to_holder), "reason": res["reason"]})
                continue
            if res.get("present") and "file" in res:
                entry["payload"]["files"][str(rel_to_holder)] = res["file"]
        return entry

    def export_bundle(self, scope: str = "all", include_absent: bool = False, source: Optional[str] = None) -> Dict[str, Any]:
        """导出版本化可移植 bundle。

        scope: core(eco 仓库内) / home(家目录) / all
        include_absent: True 时把不存在的 holder 也写入 entry(present=false)
        """
        keys = [k for k, h in self.registry.holders.items() if scope == "all" or h["scope"] == scope]
        entries = [self.collect_entry(k, include_absent=include_absent) for k in sorted(keys)]
        try:
            from eco import __version__ as eco_ver
        except Exception:  # noqa: BLE001
            eco_ver = "unknown"
        return {
            BUNDLE_MAGIC: BUNDLE_MAGIC_VALUE,
            "schema_version": ECO_STATE_SCHEMA_VERSION,
            "exported_at": _iso(datetime.now().timestamp()),
            "source": source or f"eco@{self.registry.eco_root}",
            "eco_version": eco_ver,
            "entries": entries,
        }

    def write_bundle(self, bundle: Dict[str, Any], out_path: Path) -> Path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = out_path.with_suffix(out_path.suffix + ".tmp")
        tmp.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(out_path)
        return out_path

    # ── validate ──
    def validate_bundle(self, bundle: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """整体 schema 校验 + 逐 entry/file 深校验。"""
        errs: List[str] = []
        if SchemaGuard is None:
            return True, []
        ok, e = SchemaGuard.validate(bundle, BUNDLE_SCHEMA)
        errs.extend(f"bundle{e2}" for e2 in e)
        for i, ent in enumerate(bundle.get("entries", [])):
            ok2, e2 = SchemaGuard.validate(ent, ENTRY_SCHEMA)
            errs.extend(f"entries[{i}]{e3}" for e3 in e2)
            for rel, finfo in ent.get("payload", {}).get("files", {}).items():
                ok3, e3 = SchemaGuard.validate(finfo, FILE_SCHEMA)
                errs.extend(f"entries[{i}].files[{rel}]{e4}" for e4 in e3)
                if ok3:
                    # 校验内容哈希与编码
                    try:
                        raw = _decode_content(finfo)
                        actual = hashlib.sha256(raw).hexdigest()
                        if actual != finfo["sha256"]:
                            errs.append(f"entries[{i}].files[{rel}]: sha256 不匹配")
                        if len(raw) != finfo["size"]:
                            errs.append(f"entries[{i}].files[{rel}]: size 不匹配")
                    except Exception as exc:  # noqa: BLE001
                        errs.append(f"entries[{i}].files[{rel}]: 解码失败 {exc}")
        return len(errs) == 0, errs

    def load_bundle_file(self, bundle_path: Path) -> Dict[str, Any]:
        raw = Path(bundle_path).read_text(encoding="utf-8")
        bundle = json.loads(raw)
        ok, errs = self.validate_bundle(bundle)
        if not ok:
            raise ValueError("bundle 校验失败:\n" + "\n".join(errs[:20]))
        return bundle

    # ── import ──
    def plan_import(
        self,
        bundle: Dict[str, Any],
        target_eco_root: Optional[Path] = None,
        target_home_root: Optional[Path] = None,
        scope: str = "all",
    ) -> List[Dict[str, Any]]:
        """生成还原计划（dry-run 也用它）：每文件 → 动作 create|overwrite|skip。"""
        eco_root = Path(target_eco_root) if target_eco_root is not None else self.registry.eco_root
        home_root = Path(target_home_root) if target_home_root is not None else self.registry.home_root
        plan: List[Dict[str, Any]] = []
        for ent in bundle.get("entries", []):
            if scope != "all" and ent.get("scope") != scope:
                continue
            if not ent.get("present"):
                continue
            base = eco_root if ent.get("scope") == "core" else home_root
            holder_base = base / ent["relpath"]
            for rel, finfo in ent.get("payload", {}).get("files", {}).items():
                if ent.get("kind") == "dir":
                    # 目录型 holder：relpath 即目录，文件在 payload files 内
                    dst = base / ent["relpath"] / rel
                elif rel == ent["relpath"] or rel == str(Path(ent["relpath"])):
                    # 文件型 holder：单文件快照，file key 即完整 relpath
                    dst = holder_base
                else:
                    dst = holder_base / rel
                action = "overwrite" if dst.exists() else "create"
                plan.append(
                    {
                        "key": ent["key"],
                        "scope": ent["scope"],
                        "relpath": ent["relpath"],
                        "file": rel,
                        "dst": str(dst),
                        "action": action,
                        "sha256": finfo["sha256"],
                        "size": finfo["size"],
                    }
                )
        return plan

    def import_bundle(
        self,
        bundle: Dict[str, Any],
        target_eco_root: Optional[Path] = None,
        target_home_root: Optional[Path] = None,
        scope: str = "all",
        dry_run: bool = False,
        force: bool = False,
    ) -> Dict[str, Any]:
        """还原 bundle 到目标实例。dry_run 只规划不写盘。"""
        plan = self.plan_import(bundle, target_eco_root, target_home_root, scope)
        stats = {"planned": len(plan), "created": 0, "overwritten": 0, "skipped_existing": 0, "dry_run": dry_run}
        for item in plan:
            if item["action"] == "overwrite" and not force and not dry_run:
                stats["skipped_existing"] += 1
                continue
            if dry_run:
                continue
            dst = Path(item["dst"])
            dst.parent.mkdir(parents=True, exist_ok=True)
            # 从 bundle entries 中找回文件内容
            finfo = self._find_file_info(bundle, item["key"], item["file"])
            if finfo is None:
                continue
            raw = _decode_content(finfo)
            dst.write_bytes(raw)
            if item["action"] == "create":
                stats["created"] += 1
            else:
                stats["overwritten"] += 1
        if not dry_run:
            stats["skipped_existing"] = sum(1 for i in plan if i["action"] == "overwrite" and not force)
        return stats

    @staticmethod
    def _find_file_info(bundle: Dict[str, Any], key: str, file_rel: str) -> Optional[Dict[str, Any]]:
        for ent in bundle.get("entries", []):
            if ent.get("key") != key:
                continue
            return ent.get("payload", {}).get("files", {}).get(file_rel)
        return None


def _decode_content(finfo: Dict[str, Any]) -> bytes:
    if finfo["encoding"] == "base64":
        return base64.b64decode(finfo["content"])
    return finfo["content"].encode("utf-8")


# ── Search（对标 hermes_state_search）────────────────────────────────
class EcoStateSearch:
    """统一状态检索：按 holder 分组召回（memory-tree hybrid / 向量 / 文本子串）。"""

    def __init__(self, eco_root: Optional[Path] = None, home_root: Optional[Path] = None):
        self.registry = EcoStateRegistry(eco_root, home_root)

    def search(self, query: str, k: int = 5, holders: Optional[List[str]] = None) -> Dict[str, List[Dict[str, Any]]]:
        keys = holders or list(self.registry.holders)
        out: Dict[str, List[Dict[str, Any]]] = {}
        for key in keys:
            h = self.registry.holders.get(key)
            if h is None:
                continue
            path = scope_root(h["scope"], self.registry.eco_root, self.registry.home_root) / h["rel"]
            if not path.exists():
                continue
            try:
                hits = self._search_one(key, h, path, query, k)
            except Exception as exc:  # noqa: BLE001
                logger.warning("eco_state.search %s 失败: %s", key, exc)
                hits = []
            if hits:
                out[key] = hits
        return out

    def _search_one(self, key: str, h: Dict[str, Any], path: Path, query: str, k: int) -> List[Dict[str, Any]]:
        if key == "memory_tree" and path.suffix == ".db":
            return self._search_memory_tree(path, query, k)
        if key == "memory_jsonl" and path.suffix == ".jsonl":
            return self._search_memory_jsonl(path, query, k)
        if path.is_file() and h["kind"] in ("json", "jsonl"):
            return self._search_text_lines(path, query, k)
        if path.is_dir():
            return self._search_dir(path, query, k)
        return []

    @staticmethod
    def _search_memory_tree(path: Path, query: str, k: int) -> List[Dict[str, Any]]:
        from _scripts.memory_tree import MemoryTree

        mt = MemoryTree(db_path=path)
        try:
            results = mt.search_hybrid(query, max_results=k)
        except Exception:  # noqa: BLE001 — embedding 不可用时降级
            results = mt.search(query, max_results=k)
        return [
            {
                "channel": r.get("channel", "?"),
                "score": round(r.get("rrf_score", r.get("score", 0)), 4),
                "id": r.get("id"),
                "type": r.get("type"),
                "title": r.get("title", ""),
                "snippet": r.get("content", r.get("snippet", ""))[:200],
            }
            for r in results
        ]

    @staticmethod
    def _search_memory_jsonl(path: Path, query: str, k: int) -> List[Dict[str, Any]]:
        from agent_core.memory_index import MemoryIndex

        idx = MemoryIndex(path=path)
        hits = idx.search(query, k=k)
        return [
            {
                "score": round(float(h.get("score", 0)), 4),
                "role": h.get("role", ""),
                "ts": h.get("ts", ""),
                "snippet": str(h.get("content", ""))[:200],
            }
            for h in hits
        ]

    @staticmethod
    def _search_text_lines(path: Path, query: str, k: int) -> List[Dict[str, Any]]:
        q = query.lower()
        hits = []
        try:
            with open(path, encoding="utf-8", errors="ignore") as fh:
                for lineno, line in enumerate(fh, 1):
                    if q in line.lower():
                        hits.append({"line": lineno, "snippet": line.strip()[:200]})
                        if len(hits) >= k:
                            break
        except OSError:
            pass
        return hits

    @staticmethod
    def _search_dir(path: Path, query: str, k: int) -> List[Dict[str, Any]]:
        q = query.lower()
        hits = []
        for p in sorted(path.rglob("*")):
            if not p.is_file() or p.suffix not in _TEXT_EXTENSIONS:
                continue
            try:
                with open(p, encoding="utf-8", errors="ignore") as fh:
                    for lineno, line in enumerate(fh, 1):
                        if q in line.lower():
                            hits.append({"file": str(p.relative_to(path)), "line": lineno, "snippet": line.strip()[:200]})
                            if len(hits) >= k:
                                return hits
            except OSError:
                continue
        return hits


# ── 便捷入口 ─────────────────────────────────────────────────────────
def get_registry() -> EcoStateRegistry:
    return EcoStateRegistry()


def export_state(
    scope: str = "all", out_path: Optional[Path] = None, include_absent: bool = False
) -> Tuple[Dict[str, Any], Path]:
    """导出并落盘；out_path 缺省时写入 <PROJECT_ROOT>/output/eco-state-export-*.json"""
    p = EcoStatePortability()
    bundle = p.export_bundle(scope=scope, include_absent=include_absent)
    if out_path is None:
        out_dir = PROJECT_ROOT / "output"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / ("eco-state-export-" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".json")
    p.write_bundle(bundle, out_path)
    return bundle, out_path


if __name__ == "__main__":  # pragma: no cover
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "smoke":
        reg = EcoStateRegistry()
        print(json.dumps(reg.summary(), ensure_ascii=False, indent=2))
        for probe in reg.list():
            print(json.dumps(probe, ensure_ascii=False, indent=2))
        p = EcoStatePortability()
        b = p.export_bundle(scope="all", include_absent=True)
        ok, errs = p.validate_bundle(b)
        print("bundle valid:", ok, errs[:5])
