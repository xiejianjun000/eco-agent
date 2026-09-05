#!/usr/bin/env python3
"""
agent_core/dynamic_plugin.py — 动态插件循环（对标 DSH dynamic Cordis plugins）

define → run → stop / undefine。插件代码为单文件 Python：
    # <plugin>.py
    inject = []            # 可选：依赖服务名列表
    def apply(ctx, config):  # 必选：与 cordis 插件同契约
        ...

安全边界（如实声明）：
  - 动态代码与 server 同进程执行（importlib），能访问本机模块——按受信任
    代码对待；默认关闭（ECO_DYNAMIC_PLUGINS=1 才允许 run）
  - run 前 py_compile 语法预检；加载异常完整 traceback 作为诊断返回
  - 运行实例经 cordis ctx.plugin 装载，stop/dispose 走 Fiber 副作用回收

与 DSH 的差异：无 VM 沙箱（DSH 有 VM + 双域 instanceof 补丁）、
无客户端 half、审批以环境变量开关 + API 显式调用代替交互式审批流。
"""

from __future__ import annotations

import importlib.util
import logging
import os
import sys
import threading
import time
import traceback
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger("eco.dynamic_plugin")

DATA_DIR = Path(__file__).resolve().parent.parent / "memory-tree" / "data" / "dynamic_plugins"
DATA_DIR.mkdir(parents=True, exist_ok=True)

_ALLOWED = os.environ.get("ECO_DYNAMIC_PLUGINS", "0") == "1"


def _plugin_path(plugin_id: str) -> Path:
    return DATA_DIR / f"{plugin_id}.py"


class DynamicPluginRegistry:
    """动态插件注册表：define/list/run/stop/undefine。"""

    def __init__(self) -> None:
        self._runs: dict[str, Any] = {}  # plugin_id -> dispose 函数
        self._lock = threading.RLock()

    # ── 定义 ────────────────────────────────────────────

    def define(self, code: str, name: str = "", plugin_id: str | None = None) -> dict:
        """保存插件代码（不可变追加语义简化为覆盖式保存 + 版本注释）。"""
        pid = plugin_id or uuid.uuid4().hex[:10]
        path = _plugin_path(pid)
        header = f"# dynamic plugin: {pid}  ({name or 'unnamed'})  defined_at={time.time():.0f}\n"
        with self._lock:
            path.write_text(header + code, encoding="utf-8")
        compile_result = self._precheck(pid)
        return {"ok": compile_result.get("ok", True), "plugin_id": pid, "path": str(path), "precheck": compile_result}

    def _precheck(self, plugin_id: str) -> dict:
        path = _plugin_path(plugin_id)
        try:
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
            return {"ok": True}
        except SyntaxError as e:
            return {"ok": False, "error": f"语法错误 第{e.lineno}行: {e.msg}"}

    # ── 运行 ────────────────────────────────────────────

    def run(self, plugin_id: str, config: dict | None = None) -> dict:
        """装载并激活插件（cordis ctx.plugin 装载，返回 dispose 句柄）。"""
        if not _ALLOWED:
            return {"ok": False, "error": "动态插件默认关闭：设置 ECO_DYNAMIC_PLUGINS=1 后重启才允许 run"}
        path = _plugin_path(plugin_id)
        if not path.is_file():
            return {"ok": False, "error": f"插件未定义: {plugin_id}"}
        pre = self._precheck(plugin_id)
        if not pre["ok"]:
            return {"ok": False, "error": pre["error"]}
        with self._lock:
            if plugin_id in self._runs:
                return {"ok": False, "error": f"插件已在运行: {plugin_id}"}
        try:
            from agent_core.cordis.boot import get_app_context

            spec = importlib.util.spec_from_file_location(f"eco_dyn_{plugin_id}", path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            ctx = get_app_context()
            dispose = ctx.plugin(module, config=config or {}, plugin_id=f"dynamic:{plugin_id}")
            with self._lock:
                self._runs[plugin_id] = dispose
            return {"ok": True, "plugin_id": plugin_id, "snapshot": ctx.snapshot()["plugins"].get(f"dynamic:{plugin_id}")}
        except Exception as e:  # noqa: BLE001
            tb = traceback.format_exc(limit=12)
            logger.warning("动态插件 %s 运行失败: %s", plugin_id, e)
            return {"ok": False, "error": f"{type(e).__name__}: {e}", "diagnostics": tb}

    def stop(self, plugin_id: str) -> dict:
        with self._lock:
            dispose = self._runs.pop(plugin_id, None)
        if dispose is None:
            return {"ok": False, "error": f"插件未在运行: {plugin_id}"}
        try:
            dispose()
            return {"ok": True, "plugin_id": plugin_id}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"停止失败: {e}"}

    def undefine(self, plugin_id: str) -> dict:
        """永久删除插件（先 stop）。"""
        with self._lock:
            if plugin_id in self._runs:
                try:
                    self._runs[plugin_id]()
                except Exception:  # noqa: BLE001
                    pass
                del self._runs[plugin_id]
            path = _plugin_path(plugin_id)
            if path.is_file():
                path.unlink()
        return {"ok": True, "plugin_id": plugin_id, "removed": True}

    def list(self) -> list[dict]:
        with self._lock:
            out = []
            for path in sorted(DATA_DIR.glob("*.py")):
                pid = path.stem
                out.append(
                    {
                        "plugin_id": pid,
                        "running": pid in self._runs,
                        "size_bytes": path.stat().st_size,
                        "defined_at": path.stat().st_mtime,
                    }
                )
            return out

    def get_source(self, plugin_id: str) -> dict:
        path = _plugin_path(plugin_id)
        if not path.is_file():
            return {"ok": False, "error": f"插件未定义: {plugin_id}"}
        return {"ok": True, "plugin_id": plugin_id, "source": path.read_text(encoding="utf-8")}

    def stats(self) -> dict:
        with self._lock:
            return {"allowed": _ALLOWED, "defined": len(list(DATA_DIR.glob("*.py"))), "running": len(self._runs)}


_registry: DynamicPluginRegistry | None = None
_registry_lock = threading.Lock()


def get_dynamic_plugin_registry() -> DynamicPluginRegistry:
    global _registry
    with _registry_lock:
        if _registry is None:
            _registry = DynamicPluginRegistry()
        return _registry
