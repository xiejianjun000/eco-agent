#!/usr/bin/env python3
"""
agent_core/plugins.py — 动态插件系统

插件目录规范（plugins/<name>/）：
  plugin.yaml   元数据：name / version / description / entry / tools / permissions
  handler.py    生命周期入口：load(ctx) / unload(ctx)

安全模型：插件声明的工具经 L1-L4 风险闸门（agent_core.permissions），
未知工具默认 L3（保守），manifest 可携带 tool_risk_overrides 精确声明。

用法:
    mgr = PluginManager()
    mgr.scan()                 # 发现 plugins/ 下全部插件
    mgr.load("example")        # 热加载
    mgr.list()                 # 状态列表
    mgr.unload("example")      # 卸载（调用 handler.unload + 撤销工具注册）
"""

from __future__ import annotations

import importlib.util
import logging
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

logger = logging.getLogger("eco.plugins")

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PLUGINS_DIR = ROOT / "plugins"

RISK_LEVELS = ("L1", "L2", "L3", "L4")


@dataclass
class PluginToolSpec:
    """插件声明的工具规格。"""

    name: str
    description: str = ""
    risk_level: str = "L3"
    approval_required: bool = False


@dataclass
class PluginManifest:
    name: str
    version: str = "0.1.0"
    description: str = ""
    entry: str = "handler"
    tools: list[PluginToolSpec] = field(default_factory=list)
    permissions: dict[str, str] = field(default_factory=dict)  # tool_name -> L1..L4
    raw: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> PluginManifest:
        tools = [
            PluginToolSpec(
                name=str(t.get("name", "")),
                description=str(t.get("description", "")),
                risk_level=str(t.get("risk_level", "L3")).upper(),
                approval_required=bool(t.get("approval_required", False)),
            )
            for t in data.get("tools", [])
            if isinstance(t, dict) and t.get("name")
        ]
        manifest = cls(
            name=str(data.get("name", "")),
            version=str(data.get("version", "0.1.0")),
            description=str(data.get("description", "")),
            entry=str(data.get("entry", "handler")),
            tools=tools,
            permissions={str(k): str(v).upper() for k, v in data.get("permissions", {}).items()},
            raw=data,
        )
        # 风险级校验（from_dict 即校验，load 路径同样生效）
        for t in manifest.tools:
            if t.risk_level not in RISK_LEVELS:
                raise ValueError(f"插件 {manifest.name} 工具 {t.name} 风险级非法: {t.risk_level}")
        for tool, level in manifest.permissions.items():
            if level not in RISK_LEVELS:
                raise ValueError(f"插件 {manifest.name} 权限声明非法: {tool}={level}")
        return manifest

    @classmethod
    def load(cls, path: Path) -> PluginManifest:
        yaml_path = path / "plugin.yaml"
        if not yaml_path.is_file():
            raise FileNotFoundError(f"插件缺少 plugin.yaml: {path}")
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
        manifest = cls.from_dict(data)
        if not manifest.name:
            raise ValueError(f"plugin.yaml 缺少 name: {path}")
        return manifest


class PluginContext:
    """load(ctx)/unload(ctx) 的上下文——插件通过它注册/撤销能力，禁止直接触达系统内部。"""

    def __init__(self, plugin_name: str) -> None:
        self.plugin_name = plugin_name
        self.tools: dict[str, Callable] = {}
        self.metadata: dict[str, Any] = {}

    def register_tool(self, name: str, handler: Callable, description: str = "", risk_level: str = "L3") -> None:
        if risk_level not in RISK_LEVELS:
            raise ValueError(f"风险级非法: {risk_level}")
        if name in self.tools:
            raise ValueError(f"工具重复注册: {name}")
        self.tools[name] = handler
        self.metadata[name] = {"description": description, "risk_level": risk_level}

    def log(self, message: str) -> None:
        logger.info("[plugin:%s] %s", self.plugin_name, message)


@dataclass
class LoadedPlugin:
    manifest: PluginManifest
    dir: Path
    context: PluginContext
    loaded_at: str = ""
    status: str = "loaded"  # loaded / error / unloaded
    error: str = ""
    module: Any = None


class PluginManager:
    """插件管理器：扫描 / 热加载 / 卸载 / 状态。"""

    def __init__(self, plugins_dir: Path | str | None = None) -> None:
        self.plugins_dir = Path(plugins_dir) if plugins_dir else DEFAULT_PLUGINS_DIR
        self._loaded: dict[str, LoadedPlugin] = {}
        self._tool_owner: dict[str, str] = {}  # tool_name -> plugin_name

    # ── 发现 ─────────────────────────────────────────────

    def scan(self) -> list[dict]:
        """发现 plugins/ 下全部插件目录（不加载）。"""
        out = []
        if not self.plugins_dir.is_dir():
            return out
        for entry in sorted(self.plugins_dir.iterdir()):
            if entry.is_dir() and (entry / "plugin.yaml").is_file():
                try:
                    manifest = PluginManifest.load(entry)
                    out.append(
                        {
                            "name": manifest.name,
                            "version": manifest.version,
                            "description": manifest.description,
                            "dir": str(entry),
                            "status": "loaded" if manifest.name in self._loaded else "available",
                        }
                    )
                except (FileNotFoundError, ValueError) as e:
                    out.append({"name": entry.name, "dir": str(entry), "status": "invalid", "error": str(e)})
        return out

    # ── 生命周期 ─────────────────────────────────────────

    def load(self, name: str, force: bool = False) -> dict:
        if name in self._loaded and not force:
            return {"ok": True, "status": "already_loaded", "name": name}
        plugin_dir = self.plugins_dir / name
        if not (plugin_dir / "plugin.yaml").is_file():
            return {"ok": False, "error": f"插件不存在: {name}"}

        try:
            manifest = PluginManifest.load(plugin_dir)
        except (FileNotFoundError, ValueError) as e:
            return {"ok": False, "error": str(e)}

        entry_path = plugin_dir / f"{manifest.entry}.py"
        if not entry_path.is_file():
            return {"ok": False, "error": f"插件入口缺失: {entry_path}"}

        # 冲突检查：已注册工具不得跨插件重复
        declared = [t.name for t in manifest.tools]
        conflicts = [t for t in declared if t in self._tool_owner and self._tool_owner[t] != name]
        if conflicts and not force:
            return {"ok": False, "error": f"工具冲突（已被其他插件注册）: {conflicts}"}

        try:
            spec = importlib.util.spec_from_file_location(f"eco_plugin_{name}", entry_path)
            if spec is None or spec.loader is None:
                raise ImportError(f"无法加载插件入口: {entry_path}")
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            load_fn = getattr(module, "load", None)
            getattr(module, "unload", None)
            if not callable(load_fn):
                raise ImportError("handler 缺少 load(ctx) 入口")
        except Exception as e:  # noqa: BLE001 — 插件加载失败兜底
            logger.exception("插件加载失败: %s", name)
            return {"ok": False, "error": f"加载失败: {e}"}

        ctx = PluginContext(name)
        from datetime import datetime

        try:
            result = load_fn(ctx)
        except Exception as e:  # noqa: BLE001
            logger.exception("插件 load() 执行失败: %s", name)
            return {"ok": False, "error": f"load() 失败: {e}"}

        # 校验注册工具与 manifest 声明一致
        for tool_name in declared:
            if tool_name not in ctx.tools:
                logger.warning("插件 %s 声明工具未注册: %s", name, tool_name)
        for tool_name in ctx.tools:
            self._tool_owner[tool_name] = name

        self._loaded[name] = LoadedPlugin(
            manifest=manifest,
            dir=plugin_dir,
            context=ctx,
            loaded_at=datetime.now().isoformat(),
            module=module,
            status="loaded",
        )
        loaded_tools = sorted(ctx.tools.keys())
        logger.info("插件已加载: %s v%s, 工具=%s", name, manifest.version, loaded_tools)
        return {
            "ok": True,
            "status": "loaded",
            "name": name,
            "tools": loaded_tools,
            "result": result if isinstance(result, dict) else {},
        }

    def unload(self, name: str) -> dict:
        loaded = self._loaded.get(name)
        if loaded is None:
            return {"ok": False, "error": f"插件未加载: {name}"}
        try:
            unload_fn = getattr(loaded.module, "unload", None)
            if callable(unload_fn):
                unload_fn(loaded.context)
        except Exception:  # noqa: BLE001
            logger.exception("插件 unload() 执行失败: %s", name)
        for tool_name in loaded.context.tools:
            self._tool_owner.pop(tool_name, None)
        del self._loaded[name]
        logger.info("插件已卸载: %s", name)
        return {"ok": True, "status": "unloaded", "name": name}

    def reload(self, name: str) -> dict:
        if name in self._loaded:
            unloaded = self.unload(name)
            if not unloaded["ok"]:
                return unloaded
        return self.load(name)

    # ── 查询 ─────────────────────────────────────────────

    def list(self) -> list[dict]:
        out = []
        for p in self.scan():
            loaded = self._loaded.get(p["name"])
            if loaded:
                p["status"] = loaded.status
                p["loaded_at"] = loaded.loaded_at
                p["tools"] = sorted(loaded.context.tools.keys())
            out.append(p)
        return out

    def get(self, name: str) -> dict | None:
        loaded = self._loaded.get(name)
        if loaded is None:
            for p in self.scan():
                if p["name"] == name:
                    return p
            return None
        return {
            "name": name,
            "version": loaded.manifest.version,
            "description": loaded.manifest.description,
            "status": loaded.status,
            "loaded_at": loaded.loaded_at,
            "tools": sorted(loaded.context.tools.keys()),
            "dir": str(loaded.dir),
        }

    def call_tool(self, tool_name: str, arguments: dict | None = None) -> Any:
        """调用插件注册的工具（经 L1-L4 风险闸门，插件 manifest 声明作为覆盖）。"""
        owner = self._tool_owner.get(tool_name)
        if owner is None:
            raise KeyError(f"插件工具不存在: {tool_name}")
        loaded = self._loaded[owner]
        # manifest 声明（tools.risk_level + permissions）作为风险覆盖注入闸门
        overrides: dict[str, str] = {t.name: t.risk_level for t in loaded.manifest.tools}
        overrides.update(loaded.manifest.permissions)
        from agent_core.permissions import gate_tool_call

        allowed, level, reason = gate_tool_call(tool_name, arguments, overrides=overrides)
        if not allowed:
            raise PermissionError(f"工具 {tool_name} 被权限闸门拒绝 ({level}): {reason}")
        handler = loaded.context.tools[tool_name]
        return handler(**(arguments or {}))


def get_plugin_manager(plugins_dir: Path | str | None = None) -> PluginManager:
    """进程级单例（惰性创建）。"""
    global _default_manager
    if _default_manager is None:
        _default_manager = PluginManager(plugins_dir)
    return _default_manager


_default_manager: PluginManager | None = None
