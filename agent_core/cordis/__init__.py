#!/usr/bin/env python3
"""
agent_core/cordis/__init__.py — mini-Cordis 组合内核（对标 DSH vendor/cordis）

Python 版插件模型，保留 Cordis 的核心语义：
  - Plugin：apply(ctx) 消费服务/监听事件/注册副作用；inject 声明硬依赖
  - Service：provide 提供；ctx.get(name) 可选读取（未提供返回 None）；
    声明在 inject 的插件在依赖缺失时挂起（pending），服务出现后自动激活
  - Event：on/once/emit/waterfall/bail 五种派发模式
  - Fiber：每个插件一个作用域，ctx.effect()/ctx.on()/ctx.set_interval() 等
    返回/注册 disposer，卸载时逆序执行，保证副作用可逆
  - 生命周期：pending → active → disposed（更新/卸载自动回收）
  - 组合：load_composition(yaml_path) 从 eco.cordis.yml 装配实例，
    条目形如 {plugin: 模块路径, config: {...}, inject: [...]}

与 DSH 的差异（如实声明）：
  - 无 isolate realm（单应用不需要多作用域隔离）
  - 无类型契约（Python 动态语言，靠命名约定）
  - 事件为同步派发（async 场景由 handler 内部处理）
"""

from __future__ import annotations

import importlib
import logging
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

logger = logging.getLogger("eco.cordis")

_EVENT_NAMES = ("on", "once", "emit", "waterfall", "bail")


class Disposable:
    """可回收副作用句柄。"""

    def __init__(self, dispose: Callable[[], Any], label: str = "") -> None:
        self._dispose = dispose
        self._disposed = False
        self.label = label

    def __call__(self) -> Any:
        if not self._disposed:
            self._disposed = True
            return self._dispose()
        return None

    @property
    def disposed(self) -> bool:
        return self._disposed


class _Timer:
    """定时器封装（ctx.set_interval / ctx.set_timeout）。"""

    def __init__(self, fn: Callable, interval: float, repeat: bool, label: str = "") -> None:
        self._fn = fn
        self._interval = interval
        self._repeat = repeat
        self._stop = threading.Event()
        self.label = label
        self._thread = threading.Thread(target=self._loop, daemon=True, name=f"eco-cordis-timer-{label or id(self)}")
        self._thread.start()

    def _loop(self) -> None:
        try:
            while not self._stop.wait(self._interval):
                if self._stop.is_set():
                    return
                try:
                    self._fn()
                except Exception:  # noqa: BLE001 — 定时任务异常不中断循环
                    logger.exception("cordis timer %s failed", self.label)
                if not self._repeat:
                    return
        except Exception:  # noqa: BLE001
            pass

    def dispose(self) -> None:
        self._stop.set()


class Context:
    """组合上下文：服务注册表 + 事件总线 + 插件生命周期。"""

    def __init__(self, name: str = "root", parent: Context | None = None) -> None:
        self.name = name
        self.parent = parent
        self._services: dict[str, Any] = {}
        self._service_owners: dict[str, str | None] = {}
        self._plugins: dict[str, _Fiber] = {}
        self._handlers: dict[str, list[tuple[str | None, Callable, bool]]] = {}
        self._fiber: _Fiber | None = None  # 当前加载中的 fiber（插件 apply 内使用）
        self._isolates: dict[str, Context] = {}  # label → 隔离子域（DSH isolate）

    # ── 服务 ─────────────────────────────────────────────

    def provide(self, name: str, value: Any, overwrite: bool = False) -> Any:
        """提供服务。默认拒绝覆盖（除非 overwrite）。"""
        if name in self._services and not overwrite:
            raise RuntimeError(f"服务已存在且未允许覆盖: {name}")
        self._services[name] = value
        # 服务属主 = 当前加载中的 fiber（DSH Impl 绑定 fiber，卸载自动注销）
        self._service_owners[name] = self._fiber.plugin_id if self._fiber else "root"
        self._activate_pending()
        return value

    def get(self, name: str, default: Any = None) -> Any:
        """可选读取服务：未提供返回 default（DSH ctx.get 语义）。"""
        return self._services.get(name, default)

    def __getattr__(self, name: str) -> Any:
        # 允许 ctx.xxx 直读已提供服务；未提供抛 AttributeError（诚实暴露）
        if name.startswith("_"):
            raise AttributeError(name)
        svc = self._services.get(name)
        if svc is None:
            raise AttributeError(f"服务 '{name}' 未提供——请用 ctx.get('{name}') 做可选读取")
        return svc

    # ── 事件 ─────────────────────────────────────────────

    def on(self, event: str, handler: Callable, *, global_: bool = False) -> Disposable:
        """注册事件监听（随当前 fiber 卸载自动移除）。"""
        return self._register_handler(event, handler, once=False, global_=global_)

    def once(self, event: str, handler: Callable, *, global_: bool = False) -> Disposable:
        return self._register_handler(event, handler, once=True, global_=global_)

    def emit(self, event: str, *args: Any, **kwargs: Any) -> list[Any]:
        """同步派发：返回全部 handler 结果列表（DSH emit 语义）。"""
        results = []
        for entry in list(self._handlers.get(event, [])):
            _, handler, once = entry
            try:
                results.append(handler(*args, **kwargs))
            except Exception:  # noqa: BLE001
                logger.exception("event %s handler failed", event)
            finally:
                if once:
                    self._remove_entry(event, entry)
        return results

    def serial(self, event: str, *args: Any, **kwargs: Any) -> list[Any]:
        """串行派发：顺序执行，任一 handler 抛错即中止（DSH serial 语义）。"""
        results = []
        for entry in list(self._handlers.get(event, [])):
            _, handler, once = entry
            try:
                results.append(handler(*args, **kwargs))
            finally:
                if once:
                    self._remove_entry(event, entry)
        return results

    def isolate(self, label: str = "") -> Context:
        """隔离域：子作用域快照继承当前服务/插件，域内变更不回写父域；
        同 label 复用同一隔离域（DSH isolate 语义）。"""
        if label and label in self._isolates:
            return self._isolates[label]
        child = Context(name=f"{self.name}.iso", parent=self)  # type: ignore[call-arg]
        child._services.update(self._services)  # noqa: SLF001
        child._plugins.update(self._plugins)  # noqa: SLF001
        if label:
            self._isolates[label] = child
        return child

    def waterfall(self, event: str, initial: Any, *args: Any, **kwargs: Any) -> Any:
        """串行传递：每个 handler 的返回值作为下一个的入参（DSH waterfall 语义）。"""
        value = initial
        for entry in list(self._handlers.get(event, [])):
            _, handler, once = entry
            try:
                value = handler(value, *args, **kwargs)
            except Exception:  # noqa: BLE001
                logger.exception("waterfall %s handler failed", event)
            finally:
                if once:
                    self._remove_entry(event, entry)
        return value

    def bail(self, event: str, *args: Any, **kwargs: Any) -> Any:
        """短路派发：第一个非 None 返回值即返回（DSH bail 语义）。"""
        for entry in list(self._handlers.get(event, [])):
            _, handler, once = entry
            try:
                result = handler(*args, **kwargs)
            except Exception:  # noqa: BLE001
                logger.exception("bail %s handler failed", event)
                if once:
                    self._remove_entry(event, entry)
                continue
            if once:
                self._remove_entry(event, entry)
            if result is not None:
                return result
        return None

    def _remove_entry(self, event: str, entry: tuple) -> None:
        try:
            self._handlers.get(event, []).remove(entry)
        except ValueError:
            pass

    def _register_handler(self, event: str, handler: Callable, *, once: bool, global_: bool) -> Disposable:
        fiber_id = None if global_ else (self._fiber.plugin_id if self._fiber else "root")
        entry = (fiber_id, handler, once)
        self._handlers.setdefault(event, []).append(entry)

        def dispose() -> None:
            try:
                self._handlers.get(event, []).remove(entry)
            except ValueError:
                pass

        disposable = Disposable(dispose, label=f"on({event})")
        if self._fiber is not None:
            self._fiber._disposables.append(disposable)  # noqa: SLF001
        return disposable

    # ── 副作用（Fiber 回收） ─────────────────────────────

    def effect(self, fn: Callable | None = None, label: str = "") -> Disposable:
        """注册副作用回收：fn 为 disposer（卸载时调用）。
        也支持 ctx.effect(lambda: register(...)) 形式——DSH 语义里立即执行
        并收集返回的 disposer，此处简化为直接注册 disposer。"""
        disposable = Disposable(fn or (lambda: None), label=label)
        if self._fiber is not None:
            self._fiber._disposables.append(disposable)  # noqa: SLF001
        return disposable

    def set_interval(self, fn: Callable, interval: float, label: str = "") -> Disposable:
        timer = _Timer(fn, interval, repeat=True, label=label)
        disposable = Disposable(timer.dispose, label=f"interval:{label}")
        if self._fiber is not None:
            self._fiber._disposables.append(disposable)  # noqa: SLF001
        return disposable

    def set_timeout(self, fn: Callable, delay: float, label: str = "") -> Disposable:
        timer = _Timer(fn, delay, repeat=False, label=label)
        disposable = Disposable(timer.dispose, label=f"timeout:{label}")
        if self._fiber is not None:
            self._fiber._disposables.append(disposable)  # noqa: SLF001
        return disposable

    # ── 插件生命周期 ─────────────────────────────────────

    def plugin(self, plugin: Any, config: dict | None = None, plugin_id: str | None = None) -> Callable[[], Any]:
        """加载插件：返回 dispose 函数（卸载该插件及其全部副作用）。"""
        pid = plugin_id or getattr(plugin, "__name__", plugin.__class__.__name__)
        if pid in self._plugins:
            raise RuntimeError(f"插件已加载: {pid}")
        fiber = _Fiber(self, pid, plugin, config or {})
        self._plugins[pid] = fiber
        fiber.start()
        return fiber.dispose

    def stop(self) -> None:
        """卸载全部插件（逆序回收副作用）。"""
        for pid in list(reversed(list(self._plugins.keys()))):
            try:
                self._plugins[pid].dispose()
            except Exception:  # noqa: BLE001
                logger.exception("stop plugin %s failed", pid)

    def _activate_pending(self) -> None:
        for fiber in list(self._plugins.values()):
            if fiber.status == "pending":
                fiber._try_activate()  # noqa: SLF001

    def snapshot(self) -> dict:
        return {
            "services": sorted(self._services.keys()),
            "plugins": {pid: f.status for pid, f in self._plugins.items()},
            "events": {e: len(h) for e, h in self._handlers.items()},
        }


class _Fiber:
    """插件作用域：状态机 + disposer 收集。"""

    def __init__(self, ctx: Context, plugin_id: str, plugin: Any, config: dict) -> None:
        self.ctx = ctx
        self.plugin_id = plugin_id
        self.plugin = plugin
        self.config = config
        self.status = "pending"
        self._disposables: list[Disposable] = []

    def start(self) -> None:
        self._try_activate()

    def _try_activate(self) -> None:
        if self.status != "pending":
            return
        inject = list(getattr(self.plugin, "inject", None) or [])
        missing = [name for name in inject if name not in self.ctx._services]  # noqa: SLF001
        if missing:
            logger.info("plugin %s 等待依赖: %s", self.plugin_id, missing)
            return  # 保持 pending，服务出现后由 _activate_pending 重试
        try:
            self.status = "active"
            prev = self.ctx._fiber  # noqa: SLF001
            self.ctx._fiber = self  # noqa: SLF001
            try:
                apply = getattr(self.plugin, "apply", None)
                if apply is None:
                    raise TypeError(f"插件缺少 apply(ctx): {self.plugin_id}")
                apply(self.ctx, self.config)
            finally:
                self.ctx._fiber = prev  # noqa: SLF001
        except Exception as e:  # noqa: BLE001
            self.status = "failed"
            logger.exception("plugin %s 加载失败", self.plugin_id)
            raise RuntimeError(f"插件 {self.plugin_id} 加载失败: {e}") from e

    def dispose(self) -> None:
        if self.status == "disposed":
            return
        self.status = "disposed"
        # 注销本插件提供的服务（DSH fiber unload 自动注销语义）
        for name in list(self.ctx._service_owners.keys()):  # noqa: SLF001
            if self.ctx._service_owners[name] == self.plugin_id:  # noqa: SLF001
                self.ctx._services.pop(name, None)  # noqa: SLF001
                self.ctx._service_owners.pop(name, None)  # noqa: SLF001
        # 逆序回收（DSH DisposableList 语义）
        for d in reversed(self._disposables):
            try:
                d()
            except Exception:  # noqa: BLE001
                logger.exception("disposer %s failed", d.label)


# ── 组合加载 ─────────────────────────────────────────────


def load_composition(path: str | Path, ctx: Context | None = None, base_dir: str | Path | None = None) -> Context:
    """从 YAML 组合文件装配实例（对标 DSH cordis.yml）。

    条目格式：
      - plugin: agent_core.cordis_plugins.subagent_cleaner   # 模块路径
                # （模块级 apply(ctx, config)，或模块内含 inject 声明类自动实例化）
      - plugin: package.module:PluginClass                    # 显式类路径
        config: {interval: 30}
        inject: [lessons]
    """
    import yaml

    ctx = ctx or Context(name=Path(path).stem)
    with open(path, encoding="utf-8") as f:
        entries = yaml.safe_load(f) or []
    for entry in entries:
        ref = entry["plugin"]
        config = entry.get("config") or {}
        inject = entry.get("inject") or []
        if ":" in ref and "." in ref.split(":")[0]:
            module_path, cls_name = ref.split(":", 1)
            module = importlib.import_module(module_path)
            plugin = getattr(module, cls_name)
        else:
            module = importlib.import_module(ref)
            plugin = module
            # 模块内声明 inject 的类 → 自动实例化（插件类约定）
            for attr_name in dir(module):
                obj = getattr(module, attr_name)
                if isinstance(obj, type) and obj.__module__ == module.__name__ and hasattr(obj, "inject"):
                    plugin = obj()
                    break
        if inject:
            plugin.inject = list(inject)  # 类/模块级声明
        ctx.plugin(plugin, config=config, plugin_id=ref)
    return ctx
