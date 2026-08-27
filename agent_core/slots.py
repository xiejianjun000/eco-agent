#!/usr/bin/env python3
"""
agent_core/slots.py — Slot 注册表（对标 DSH Slot 系统，Python 简化版）

面板挂点：side.tab（右侧栏标签页）。插件注册面板后，前端从
GET /api/v1/slots 动态渲染标签与内容（数据经 GET /api/v1/slots/{id}/data）。

与 DSH 的差异（如实声明）：
  - DSH 的 Slot 注册的是 Client 端 React 组件（代码级 UI）；
    本实现注册的是「面板描述 + 数据提供器」，前端按通用列表/表格渲染，
    扩展性弱于 DSH，但零前端重建即可挂新面板。
"""

from __future__ import annotations

import threading
from typing import Any, Callable

# 已知挂点
SLOT_NAMES = ("side.tab",)


class SlotRegistry:
    """面板注册表：slot_name → [panel, ...]。"""

    def __init__(self) -> None:
        self._slots: dict[str, list[dict]] = {}
        self._lock = threading.RLock()

    def register(self, slot_name: str, panel: dict) -> dict:
        """注册面板。panel = {id, title, description, provider?}。
        provider: 无参 callable → 面板数据 dict（延迟调用，序列化时不透出）。"""
        if slot_name not in SLOT_NAMES:
            raise ValueError(f"未知挂点: {slot_name}（可用: {SLOT_NAMES}）")
        with self._lock:
            self._slots.setdefault(slot_name, []).append(panel)
        return panel

    def list(self, slot_name: str | None = None) -> list[dict]:
        """序列化面板清单（provider 不透出）。"""
        with self._lock:
            slots = self._slots if slot_name is None else {slot_name: self._slots.get(slot_name, [])}
            out = []
            for name, panels in slots.items():
                for p in panels:
                    out.append({
                        "slot": name,
                        "id": p.get("id"),
                        "title": p.get("title"),
                        "description": p.get("description", ""),
                    })
            return out

    def get_data(self, panel_id: str) -> dict:
        """调用面板数据提供器，返回 {panel_id, ...数据}。"""
        with self._lock:
            for panels in self._slots.values():
                for p in panels:
                    if p.get("id") == panel_id:
                        provider = p.get("provider")
                        if provider is None:
                            return {"panel_id": panel_id, "error": "面板无数据提供器"}
                        try:
                            data = provider()
                            return {"panel_id": panel_id, "title": p.get("title"), **data}
                        except Exception as e:  # noqa: BLE001
                            return {"panel_id": panel_id, "error": f"{type(e).__name__}: {e}"}
        return {"panel_id": panel_id, "error": "面板不存在"}

    def stats(self) -> dict:
        with self._lock:
            return {name: len(panels) for name, panels in self._slots.items()}


_registry: SlotRegistry | None = None
_registry_lock = threading.Lock()


def get_slot_registry() -> SlotRegistry:
    global _registry
    with _registry_lock:
        if _registry is None:
            _registry = SlotRegistry()
        return _registry
