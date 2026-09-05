#!/usr/bin/env python3
"""
agent_core/memory_curation.py — 记忆策展（A-04 矛盾检测 + A-05 遗忘曲线）

验收口径:
  A-04 跨会话记忆一致性: 四层记忆矛盾须在 24h 内标记并消解
  A-05 遗忘曲线正确性: 情景记忆按艾宾浩斯曲线衰减，关键事实永久豁免

设计:
  - 在 CrossSessionMemory 之上做策展层，不侵入原存储结构
  - 遗忘: episodic 条目 recall 时按 R(t)=e^(-t/S) 加权（S=1 天），
    权重 < 阈值视为"待归档"；semantic/procedural 标记 permanent 的不衰减
  - 矛盾: semantic 层同 key 冲突版本记录到 conflict 登记表（含双方值+时间），
    心跳（L3 Pulse）调 resolve_conflicts() 消解：保留最新 + 审计记录
"""

from __future__ import annotations

import json
import logging
import math
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("eco.memory_curation")

DATA_DIR = Path(__file__).resolve().parent.parent / "memory-tree" / "data"

# 艾宾浩斯简化参数：R(t) = e^(-t/S)，S=1 天；< FORGET_THRESHOLD 视为待归档
FORGET_S = 1.0  # 衰减时间常数（天）
FORGET_THRESHOLD = 0.25  # 权重阈值
CONFLICT_RESOLVE_HOURS = 24  # A-04：24 小时内消解


class MemoryCurator:
    """记忆策展器：遗忘曲线 + 矛盾检测/消解。"""

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = Path(base_dir) if base_dir else DATA_DIR
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._conflicts_path = self.base_dir / "memory_conflicts.json"
        self._audit_path = self.base_dir / "memory_curation_audit.jsonl"
        self._lock = threading.RLock()

    # ── A-05 遗忘曲线 ─────────────────────────────────────

    @staticmethod
    def retention_weight(age_seconds: float, permanent: bool = False) -> float:
        """艾宾浩斯保留权重 R(t)=e^(-t/S)。permanent 恒为 1.0。"""
        if permanent:
            return 1.0
        days = max(0.0, age_seconds / 86400.0)
        return math.exp(-days / FORGET_S)

    def score_episodic(self, episodic: list[dict], now: datetime | None = None) -> list[dict]:
        """给情景记忆列表附加衰减权重与状态（active/forgotten）。"""
        now = now or datetime.now()
        out = []
        for entry in episodic:
            try:
                ts = datetime.fromisoformat(entry["timestamp"])
            except (KeyError, ValueError):
                ts = now
            age = (now - ts).total_seconds()
            weight = self.retention_weight(age, permanent=bool(entry.get("permanent")))
            out.append(
                {
                    **entry,
                    "retention_weight": round(weight, 4),
                    "status": "active" if weight >= FORGET_THRESHOLD else "forgotten",
                }
            )
        return out

    def recall_episodic(
        self, episodic: list[dict], keyword: str = "", top_k: int = 10, now: datetime | None = None
    ) -> list[dict]:
        """按遗忘权重召回情景记忆（遗忘的仍可检索但排在最后）。"""
        scored = self.score_episodic(episodic, now=now)
        if keyword:
            k = keyword.lower()
            scored = [
                s
                for s in scored
                if k in str(s.get("event", "")).lower() or k in json.dumps(s.get("context", {}), ensure_ascii=False).lower()
            ]
        scored.sort(key=lambda s: (s["status"] == "forgotten", -s["retention_weight"]))
        return scored[:top_k]

    # ── A-04 矛盾检测/消解 ────────────────────────────────

    def detect_conflicts(self, semantic: dict[str, Any]) -> list[dict]:
        """登记语义层矛盾：同 key 出现不同值（在 24h 内被 resolve 处理）。"""
        conflicts = self._load_conflicts()
        resolved_keys = set()
        for key, entry in semantic.items():
            value = entry.get("value") if isinstance(entry, dict) else entry
            updated = entry.get("updated_at") if isinstance(entry, dict) else None
            for c in conflicts:
                if c["key"] == key and c["status"] == "open" and c["current_value"] != str(value):
                    c["conflicting_value"] = str(value)
                    c["conflicting_at"] = updated
                    resolved_keys.add(key)
        self._save_conflicts(conflicts)
        return [c for c in conflicts if c["key"] in resolved_keys and c["status"] == "open"]

    def register_value(self, key: str, value: Any, permanent: bool = False) -> None:
        """语义层写入时登记值，用于后续矛盾发现。"""
        conflicts = self._load_conflicts()
        conflicts.append(
            {
                "key": key,
                "current_value": str(value)[:500],
                "conflicting_value": None,
                "registered_at": datetime.now().isoformat(),
                "status": "open",
                "permanent": permanent,
            }
        )
        self._save_conflicts(conflicts)

    def resolve_conflicts(self, semantic: dict[str, Any], now: datetime | None = None) -> dict:
        """消解超 24h 的开放矛盾：保留最新值，写审计链。返回处理统计。"""
        now = now or datetime.now()
        conflicts = self._load_conflicts()
        resolved = 0
        for c in conflicts:
            if c["status"] != "open":
                continue
            if c.get("permanent"):
                continue  # 永久事实的矛盾须人工裁决，不自动消解
            try:
                opened = datetime.fromisoformat(c["registered_at"])
            except ValueError:
                opened = now
            if (now - opened).total_seconds() < CONFLICT_RESOLVE_HOURS * 3600:
                continue  # 未到 24h，保持开放（A-04 时限内等待观察）
            # 消解策略：语义层当前值胜出，登记历史
            key = c["key"]
            current = semantic.get(key)
            current_value = current.get("value") if isinstance(current, dict) else current
            c["status"] = "resolved"
            c["resolved_at"] = now.isoformat()
            c["winner"] = str(current_value)[:500]
            self._audit(
                {
                    "action": "conflict_resolved",
                    "key": key,
                    "loser": c["current_value"],
                    "winner": c["winner"],
                    "opened_at": c["registered_at"],
                }
            )
            resolved += 1
        self._save_conflicts(conflicts)
        return {"resolved": resolved, "open": sum(1 for c in conflicts if c["status"] == "open")}

    # ── 统计 / 内部 ───────────────────────────────────────

    def stats(self) -> dict:
        conflicts = self._load_conflicts()
        return {
            "open_conflicts": sum(1 for c in conflicts if c["status"] == "open"),
            "resolved_conflicts": sum(1 for c in conflicts if c["status"] == "resolved"),
            "audit_entries": sum(1 for _ in self._audit_lines()),
        }

    def _load_conflicts(self) -> list[dict]:
        if self._conflicts_path.exists():
            try:
                data = json.loads(self._conflicts_path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return data
            except (json.JSONDecodeError, OSError):
                logger.warning("memory_conflicts.json 损坏，重建")
        return []

    def _save_conflicts(self, conflicts: list[dict]) -> None:
        with self._lock:
            self._conflicts_path.write_text(json.dumps(conflicts, ensure_ascii=False, indent=2), encoding="utf-8")

    def _audit(self, entry: dict) -> None:
        entry = {**entry, "time": datetime.now().isoformat()}
        with self._lock, self._audit_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def _audit_lines(self):
        if not self._audit_path.exists():
            return []
        return self._audit_path.read_text(encoding="utf-8", errors="replace").splitlines()


def get_memory_curator(base_dir: Path | None = None) -> MemoryCurator:
    global _default_curator
    if _default_curator is None:
        _default_curator = MemoryCurator(base_dir)
    return _default_curator


_default_curator: MemoryCurator | None = None
