#!/usr/bin/env python3
"""
agent_core/domain_focus.py — 要素专注模式（要素域锁定状态机）
====================================================================
设计（军哥）：
  1. 用户显式声明部门/职责（"我是大气科的/我负责水环境/执法支队/环评"）→ 立即锁定要素域；
  2. 用户连续 ≥3 轮问同一要素 → 自动锁定；
  3. 锁定后：回答只围绕该要素精准给（术语/标准/法规口径对齐该域），
     用户问其他要素时先一句确认是否切换；
  4. "全要素/解除专注/取消锁定" → 解锁回到全要素。

域识别复用 agent_core.domains.classify_domain（单一权威源）。
状态按会话维度持久化（memory-tree/data/domain_focus.json）。
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path

from agent_core.domains import ALL_DOMAINS, classify_domain

logger = logging.getLogger("eco.domain_focus")

DATA_DIR = Path(__file__).resolve().parent.parent / "memory-tree" / "data"
STORE = DATA_DIR / "domain_focus.json"
LOCK_THRESHOLD = 3  # 连续同域轮数达到即锁定

# 显式声明 → 域 映射（部门/职责口语 → 域 id）
DECLARE_MAP: dict[str, str] = {
    "大气": "atmosphere", "气科": "atmosphere", "废气": "atmosphere",
    "水环境": "water", "水科": "water", "地表水": "water", "废水": "water",
    "土壤": "soil", "土科": "soil", "地块": "soil",
    "固废": "solid_waste", "危废": "solid_waste", "固体废物": "solid_waste",
    "噪声": "noise", "声环境": "noise",
    "辐射": "radiation", "核": "radiation", "放射": "radiation",
    "生态": "ecology", "自然保护地": "ecology", "生物多样性": "ecology",
    "碳": "carbon", "气候": "carbon", "温室气体": "carbon",
    "环评": "eia", "环境影响评价": "eia",
    "排污许可": "permit", "许可": "permit",
    "执法": "enforcement", "监察": "enforcement", "支队": "enforcement",
    "督察": "inspection", "应急": "emergency", "监测": "monitoring",
}
# 域中文名（declared 域若不在 ALL_DOMAINS 里，用声明词本身做 label）
UNLOCK_WORDS = ("全要素", "解除专注", "取消专注", "取消锁定", "解除锁定",
                "回到全要素", "退出专注", "通用模式")


class DomainFocus:
    """会话级要素专注状态机。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._state: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        try:
            if STORE.is_file():
                self._state = json.loads(STORE.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            self._state = {}

    def _persist(self) -> None:
        try:
            STORE.parent.mkdir(parents=True, exist_ok=True)
            STORE.write_text(json.dumps(self._state, ensure_ascii=False),
                             encoding="utf-8")
        except OSError as e:  # pragma: no cover
            logger.warning("[domain_focus] 落盘失败: %s", e)

    @staticmethod
    def _declared_domain(text: str) -> str | None:
        """显式声明检测：'我是大气科的/我负责水环境/执法支队'等。"""
        t = text or ""
        for word, did in DECLARE_MAP.items():
            if word in t and ("我是" in t or "我负责" in t or "我们" in t
                              or "我是" in t or "部门" in t or "科室" in t
                              or "支队" in t or "分管" in t or "岗位" in t):
                return did
        return None

    def update(self, session_id: str, user_msg: str) -> tuple[str | None, bool]:
        """处理一轮用户消息：返回 (专注域id 或 None, 是否刚发生锁定/解锁)。"""
        t = (user_msg or "").strip()
        with self._lock:
            st = self._state.setdefault(session_id,
                                        {"focus": None, "cand": None, "cnt": 0})
            # 解锁
            if any(w in t for w in UNLOCK_WORDS):
                changed = st["focus"] is not None
                st.update({"focus": None, "cand": None, "cnt": 0})
                self._persist()
                return None, changed
            # 显式声明 → 立即锁定
            declared = self._declared_domain(t)
            if declared and declared in ALL_DOMAINS:
                changed = st["focus"] != declared
                st.update({"focus": declared, "cand": declared, "cnt": LOCK_THRESHOLD})
                self._persist()
                return declared, changed
            # 隐式：连续同域计数
            hit = classify_domain(t) or []
            cand = hit[0] if hit else None
            if cand and cand == st.get("cand"):
                st["cnt"] += 1
            else:
                st["cand"] = cand
                st["cnt"] = 1 if cand else 0
            if (st.get("focus") is None and cand
                    and st["cnt"] >= LOCK_THRESHOLD):
                st["focus"] = cand
                self._persist()
                return cand, True
            if st.get("focus") and cand is None and st.get("cnt", 0) == 0:
                # 已锁定但本轮无关该域：保持锁定，不计入切换
                pass
            self._persist()
            return st.get("focus"), False

    def focus_of(self, session_id: str) -> str | None:
        with self._lock:
            return self._state.get(session_id, {}).get("focus")


_focus: DomainFocus | None = None


def get_domain_focus() -> DomainFocus:
    global _focus
    if _focus is None:
        _focus = DomainFocus()
    return _focus
