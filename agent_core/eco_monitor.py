#!/usr/bin/env python3
"""
agent_core/eco_monitor.py — 免 LLM 确定性巡检通道（M4 P1-2 / Hermes monitor-mode 对标）
======================================================================================
对标基准：Hermes cron job 的 ``monitor_script`` / ``monitor_url`` monitor mode。
Hermes 语义：每个定时 tick 先执行确定性巡检源并对其输出做**精确字节哈希**——
  输出未变  → 记录 silent 'no_change' tick，**完全不唤醒 LLM**（省钱/省噪音）；
  输出变化  → 注入 MONITOR CHANGE DETECTED 块后才正常跑 agent。

eco-agent 侧已有 L4 调度（memory-tree/data/scheduled_jobs.json + agent_core/scheduler.py）
与状态健康面（agent_core/eco_state.py 的 EcoStateRegistry 探针）。本模块把
monitor-mode 落为**可在 LLM tick 之前独立运行、以稳定签名驱动变更检测**的巡检通道：

  eco monitor run    一次巡检：确定性检查集 + 可选外部巡检脚本（--script），
                     输出人类可读表 + 机器可读 JSON + "SIGNATURE <sha256>"
  eco monitor watch  循环巡检：签名与上次基线比对——
                     未变 → no-change tick（exit 0，不升级 LLM）
                     变化 → MONITOR CHANGE DETECTED（exit 2，供上层唤醒 LLM，
                            可选写入 notepad kind=alert，见 eco_notepad.py）

签名稳定化（对齐 Hermes "emit stable output (no timestamps)" 契约）：
signature 只基于 (name, ok, size_bytes, record_count) 等**状态指纹**，
绝不纳入 mtime/时钟等时间戳字段，避免每 tick 假阳性变更。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("eco.monitor")

HOME_ECO_DIR = Path(os.environ.get("ECO_HOME", str(Path.home() / ".eco")))
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STATE_FILE = HOME_ECO_DIR / "monitor_state.json"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _read_jsonl_lines(path: Path) -> Tuple[int, Optional[str]]:
    """返回 (有效行数, 首个坏行错误)；空/不存在视为 0 行无错。"""
    if not path.exists():
        return 0, None
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return 0, str(exc)
    n = 0
    for line in raw.splitlines():
        if not line.strip():
            continue
        try:
            json.loads(line)
            n += 1
        except ValueError as exc:
            return n, f"第 {n + 1} 行解析失败: {exc}"
    return n, None


def _read_json_file(path: Path) -> Tuple[bool, Optional[str]]:
    if not path.exists():
        return False, "absent"
    try:
        json.loads(path.read_text(encoding="utf-8"))
        return True, None
    except (OSError, ValueError) as exc:
        return False, f"JSON 解析失败: {exc}"


def _env_api_key(provider: str) -> Tuple[bool, str]:
    """读 ~/.eco/.env 中 provider 对应 key 是否就位（绝不泄露值）。"""
    env = HOME_ECO_DIR / ".env"
    if not env.exists():
        return False, ".env absent"
    try:
        lines = env.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        return False, str(exc)
    kv: Dict[str, str] = {}
    for ln in lines:
        ln = ln.strip()
        if not ln or ln.startswith("#") or "=" not in ln:
            continue
        k, _, v = ln.partition("=")
        kv[k.strip()] = v.strip().strip('"').strip("'")
    provider = provider or kv.get("ECO_PROVIDER", "deepseek")
    ek_map = {"deepseek": "DEEPSEEK_API_KEY", "openai": "OPENAI_API_KEY", "kimi": "KIMI_API_KEY", "custom": "CUSTOM_API_KEY"}
    key_name = ek_map.get(provider, "DEEPSEEK_API_KEY")
    present = bool(kv.get(key_name)) or bool(os.environ.get(key_name))
    return present, f"{provider} {key_name} {'present' if present else 'missing'}"


# ── 确定性检查集（每项返回稳定指纹 hash_key，供签名用）─────────────
def _check_state_holders() -> Dict[str, Any]:
    try:
        from agent_core.eco_state import EcoStateRegistry

        reg = EcoStateRegistry()
        probes = reg.list()
    except Exception as exc:  # noqa: BLE001 — 巡检容错
        return {
            "name": "state_holders",
            "ok": False,
            "detail": f"registry 不可用: {exc}",
            "hash_key": ("state_holders", False, 0, 0),
        }
    healthy = sum(1 for p in probes if p.get("healthy"))
    total = len(probes)
    records = sum(p.get("record_count") or 0 for p in probes)
    bad = [p["key"] for p in probes if not p.get("healthy")]
    return {
        "name": "state_holders",
        "ok": healthy == total,
        "detail": f"{healthy}/{total} healthy, {records} records" + (f"; bad: {','.join(bad)}" if bad else ""),
        "hash_key": ("state_holders", healthy == total, total, records),
    }


def _check_env_keys() -> Dict[str, Any]:
    provider = "deepseek"
    env = HOME_ECO_DIR / ".env"
    if env.exists():
        try:
            for ln in env.read_text(encoding="utf-8").splitlines():
                if ln.strip().startswith("ECO_PROVIDER="):
                    provider = ln.strip().partition("=")[2].strip().strip('"').strip("'") or provider
        except (OSError, UnicodeDecodeError):
            pass
    present, detail = _env_api_key(provider)
    return {"name": "env_keys", "ok": present, "detail": detail, "hash_key": ("env_keys", present, 0, 0)}


def _check_tasks_ctl() -> Dict[str, Any]:
    path = HOME_ECO_DIR / "tasks"
    if not path.exists():
        return {"name": "tasks_ctl", "ok": True, "detail": "absent (未启用任务控制面)", "hash_key": ("tasks_ctl", True, 0, 0)}
    files = sorted(path.glob("*.json"))
    n_ok = 0
    errs = []
    for f in files:
        ok, err = _read_json_file(f)
        if ok:
            n_ok += 1
        else:
            errs.append(f"{f.name}:{err}")
    ok = len(errs) == 0
    return {
        "name": "tasks_ctl",
        "ok": ok,
        "detail": f"{n_ok}/{len(files)} json ok" + (f"; bad: {'|'.join(errs)}" if errs else ""),
        "hash_key": ("tasks_ctl", ok, len(files), n_ok),
    }


def _check_peers_ledger() -> Dict[str, Any]:
    path = HOME_ECO_DIR / "peers"
    if not path.exists():
        return {
            "name": "peers_ledger",
            "ok": True,
            "detail": "absent (未启用对等消息)",
            "hash_key": ("peers_ledger", True, 0, 0),
        }
    files = sorted([p for p in path.rglob("*") if p.is_file() and p.suffix in (".json", ".jsonl")])
    n_ok = 0
    errs = []
    for f in files:
        if f.suffix == ".jsonl":
            n, err = _read_jsonl_lines(f)
            if err:
                errs.append(f"{f.name}:{err}")
            else:
                n_ok += 1
        else:
            ok, err = _read_json_file(f)
            if ok:
                n_ok += 1
            else:
                errs.append(f"{f.name}:{err}")
    ok = len(errs) == 0
    return {
        "name": "peers_ledger",
        "ok": ok,
        "detail": f"{n_ok}/{len(files)} ledger ok" + (f"; bad: {'|'.join(errs)}" if errs else ""),
        "hash_key": ("peers_ledger", ok, len(files), n_ok),
    }


def _check_runtime_jsonl() -> Dict[str, Any]:
    """decisions.jsonl / stats.jsonl 只追加账本可解析性。"""
    parts = []
    n_total = 0
    ok = True
    for name in ("decisions.jsonl", "stats.jsonl"):
        p = HOME_ECO_DIR / name
        if not p.exists():
            parts.append(f"{name}:absent")
            continue
        n, err = _read_jsonl_lines(p)
        n_total += n
        if err:
            ok = False
            parts.append(f"{name}:{err}")
        else:
            parts.append(f"{name}:{n} rows")
    return {
        "name": "runtime_jsonl",
        "ok": ok,
        "detail": "; ".join(parts),
        "hash_key": ("runtime_jsonl", ok, len(parts), n_total),
    }


def _check_memory_db() -> Dict[str, Any]:
    path = PROJECT_ROOT / "memory-tree" / "data" / "eco_memory.db"
    if not path.exists():
        return {"name": "memory_db", "ok": True, "detail": "absent (未建库)", "hash_key": ("memory_db", True, 0, 0)}
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        cur = conn.execute("SELECT 1")
        cur.fetchone()
        # 只读行数不引入 mtime
        row = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()
        conn.close()
        n_tables = int(row[0]) if row else 0
        return {
            "name": "memory_db",
            "ok": True,
            "detail": f"sqlite ok, {n_tables} tables",
            "hash_key": ("memory_db", True, n_tables, 0),
        }
    except Exception as exc:  # noqa: BLE001
        return {"name": "memory_db", "ok": False, "detail": f"sqlite 不可读: {exc}", "hash_key": ("memory_db", False, 0, 0)}


def _check_scheduled_jobs() -> Dict[str, Any]:
    path = PROJECT_ROOT / "memory-tree" / "data" / "scheduled_jobs.json"
    ok, err = _read_json_file(path)
    n_jobs = 0
    if ok and path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            n_jobs = len(data.get("jobs") or [])
        except (OSError, ValueError):
            pass
    if not ok:
        return {
            "name": "scheduled_jobs",
            "ok": False,
            "detail": f"{path.name}: {err}",
            "hash_key": ("scheduled_jobs", False, 0, 0),
        }
    return {"name": "scheduled_jobs", "ok": True, "detail": f"{n_jobs} jobs", "hash_key": ("scheduled_jobs", True, n_jobs, 0)}


DEFAULT_CHECKS: List[Callable[[], Dict[str, Any]]] = [
    _check_state_holders,
    _check_env_keys,
    _check_tasks_ctl,
    _check_peers_ledger,
    _check_runtime_jsonl,
    _check_memory_db,
    _check_scheduled_jobs,
]


class EcoMonitor:
    """免 LLM 确定性巡检。run_once 产出 checks+signature，watch 做基线变更检测。"""

    def __init__(self, state_file: Optional[Path] = None):
        self.state_file = Path(state_file) if state_file else DEFAULT_STATE_FILE

    # ── 巡检一次 ──
    def run_once(
        self, checks: Optional[List[Callable[[], Dict[str, Any]]]] = None, script: Optional[str] = None
    ) -> Dict[str, Any]:
        items = [fn() for fn in (checks or DEFAULT_CHECKS)]
        extra: Dict[str, Any] = {}
        if script:
            sres = self._run_external_script(script)
            items.append(sres)
            extra["script"] = sres
        overall_ok = all(i["ok"] for i in items)
        sig = self._signature(items)
        return {
            "ts": _now(),
            "overall_ok": overall_ok,
            "checks": items,
            "signature": sig,
        }

    # ── 外部巡检脚本（对标 Hermes monitor_script）──────────────────
    @staticmethod
    def _run_external_script(script: str) -> Dict[str, Any]:
        """执行确定性巡检脚本，捕获 stdout 做精确哈希；契约同 Hermes：
        脚本应输出稳定内容（不夹时间戳），输出字节变化即视为"状态变更"。"""
        path = Path(script).expanduser()
        if not path.exists():
            return {"name": f"script:{script}", "ok": False, "detail": "script absent", "hash_key": ("script", False, 0, 0)}
        try:
            proc = subprocess.run(
                [sys.executable, str(path)] if path.suffix == ".py" else [str(path)], capture_output=True, text=True, timeout=60
            )
        except Exception as exc:  # noqa: BLE001
            return {
                "name": f"script:{path.name}",
                "ok": False,
                "detail": f"执行失败: {exc}",
                "hash_key": ("script", False, 0, 0),
            }
        if proc.returncode != 0:
            return {
                "name": f"script:{path.name}",
                "ok": False,
                "detail": f"exit {proc.returncode}: {proc.stderr.strip()[:120]}",
                "hash_key": ("script", False, 0, 0),
            }
        out = proc.stdout
        out_sha = hashlib.sha256(out.encode("utf-8")).hexdigest()
        return {
            "name": f"script:{path.name}",
            "ok": True,
            "detail": f"stdout {len(out)}B sha256={out_sha[:12]}",
            # Hermes 契约：输出精确字节哈希；hash_key 必须含内容指纹，
            # 不能只含长度（同长内容变化会漏检）
            "hash_key": ("script", True, out_sha, 0),
            "script_sha256": out_sha,
        }

    # ── 稳定签名（不含 mtime/timestamps）──────────────────────────
    @staticmethod
    def _signature(items: List[Dict[str, Any]]) -> str:
        h = hashlib.sha256()
        for it in items:
            h.update(json.dumps(it.get("hash_key"), sort_keys=True, ensure_ascii=False).encode("utf-8"))
            h.update(b"\n")
        return h.hexdigest()[:16]

    # ── watch：与上次基线比对 ─────────────────────────────────────
    def load_baseline_state(self) -> Optional[Dict[str, Any]]:
        """读基线状态文件（含 signature + 每项 hash_key 快照，供 diff）。"""
        if not self.state_file.exists():
            return None
        try:
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or "signature" not in data:
                return None
            return data
        except (OSError, ValueError):
            return None

    def load_baseline(self) -> Optional[str]:
        data = self.load_baseline_state()
        return data.get("signature") if data else None

    def save_baseline(
        self, signature: str, checks_map: Optional[Dict[str, Any]] = None, extra: Optional[Dict[str, Any]] = None
    ) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        data = {"updated_at": _now(), "signature": signature}
        if checks_map:
            data["checks"] = checks_map
        if extra:
            data.update(extra)
        tmp = self.state_file.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.state_file)

    @staticmethod
    def _diff_checks(prev_checks: Dict[str, Any], cur_checks: Dict[str, Any]) -> List[str]:
        """对比两轮 {name: hash_key} 快照，返回变化/新增/消失的检查名。
        快照经 JSON 往返后 tuple 会变 list，故统一序列化后比较，
        避免"旧基线是 tuple、内存是 list"造成的全量误报。"""

        def _norm(v: Any) -> str:
            return json.dumps(v, sort_keys=True, ensure_ascii=False)

        pk = {k: _norm(v) for k, v in (prev_checks or {}).items()}
        ck = {k: _norm(v) for k, v in (cur_checks or {}).items()}
        changed = []
        for name in sorted(set(pk) | set(ck)):
            if pk.get(name) != ck.get(name):
                changed.append(name)
        return changed

    def watch_once(self, script: Optional[str] = None) -> Dict[str, Any]:
        """单轮 watch：跑巡检并对比基线。
        返回 {status: baseline|no_change|change, report, changed_items}"""
        report = self.run_once(script=script)
        sig = report["signature"]
        checks_map = {it["name"]: it.get("hash_key") for it in report["checks"]}
        prev = self.load_baseline_state()
        if prev is None:
            self.save_baseline(sig, checks_map=checks_map, extra={"first_baseline": True})
            return {"status": "baseline", "report": report, "changed_items": []}
        if prev.get("signature") == sig:
            # 旧基线无 checks 快照时顺带升级（首次 no_change 自动补齐 diff 能力）
            if not prev.get("checks"):
                self.save_baseline(sig, checks_map=checks_map)
            return {"status": "no_change", "report": report, "changed_items": []}
        # 变化：优先按 hash_key 快照 diff（无快照的旧基线降级为 signature 变化）
        changed = self._diff_checks(prev.get("checks") or {}, checks_map) or ["signature 变化"]
        self.save_baseline(sig, checks_map=checks_map)
        return {"status": "change", "report": report, "changed_items": changed}

    def watch(
        self, interval: float = 60.0, ticks: Optional[int] = None, script: Optional[str] = None, alert_notepad: bool = False
    ) -> Dict[str, Any]:
        """循环 watch。ticks=None 无限循环（Ctrl+C 退出）。
        返回最终一次结果摘要（正常结束 ticks 或变更提前返回）。"""
        tick = 0
        last: Dict[str, Any] = {}
        while ticks is None or tick < ticks:
            tick += 1
            try:
                last = self.watch_once(script=script)
            except KeyboardInterrupt:
                raise
            status = last["status"]
            print(f"[tick {tick}] {status} sig={last['report']['signature']} ts={last['report']['ts']}")
            if status == "no_change":
                # 对齐 Hermes：无变化 = 静默 tick，不唤醒 LLM
                print("  [no-change] 巡检无变化，跳过 LLM 唤醒")
            elif status == "change":
                print("  [MONITOR CHANGE DETECTED] " + ",".join(last["changed_items"]))
                if alert_notepad:
                    self._write_alert(last)
                return last
            else:  # baseline（首次）
                print("  [baseline] 已建立巡检基线")
            if ticks is not None and tick >= ticks:
                break
            time.sleep(max(0.0, float(interval)))
        return last

    def _write_alert(self, result: Dict[str, Any]) -> None:
        try:
            from agent_core.eco_notepad import NotepadStore

            store = NotepadStore()
            store.add(
                title="monitor change detected",
                content=(
                    f"status={result['status']} changed="
                    f"{','.join(result.get('changed_items') or [])} "
                    f"sig={result['report']['signature']} "
                    f"ts={result['report']['ts']}"
                ),
                tags=["monitor", "alert"],
                kind="alert",
                ref="monitor",
            )
            print("  [alert] 已写入 notepad (kind=alert, ref=monitor)")
        except Exception as exc:  # noqa: BLE001 — 告警写盘失败不阻断 watch
            print(f"  [alert] notepad 写入失败: {exc}")
