#!/usr/bin/env python3
"""
tests/test_cordis.py — mini-Cordis 组合内核语义测试

覆盖：服务提供/读取、inject 挂起→激活、事件五模式、
disposer 逆序回收、定时器、组合加载、标准服务装配。
可直接 python3 tests/test_cordis.py 运行（不依赖 pytest）。
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent_core.cordis import Context, load_composition  # noqa: E402

PASS = 0
FAIL = 0


def check(name: str, cond: bool) -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name}")


class _Svc:
    pass


def test_services() -> None:
    print("== 服务提供/读取 ==")
    ctx = Context("t-svc")
    ctx.provide("svc", _Svc())
    check("ctx.get 可选读取", isinstance(ctx.get("svc"), _Svc))
    check("ctx.get 未提供返回 None", ctx.get("nope") is None)
    check("ctx.xxx 直读", isinstance(ctx.svc, _Svc))
    try:
        ctx.nope
        check("未提供服务直读抛 AttributeError", False)
    except AttributeError:
        check("未提供服务直读抛 AttributeError", True)
    try:
        ctx.provide("svc", _Svc())
        check("默认拒绝覆盖服务", False)
    except RuntimeError:
        check("默认拒绝覆盖服务", True)


def test_inject_activation() -> None:
    print("== inject 挂起→激活 ==")
    ctx = Context("t-inject")
    order: list[str] = []

    class P:
        inject = ["later"]

        def apply(self, ctx, config):
            order.append(f"active:{type(ctx.get('later')).__name__}")

    ctx.plugin(P(), plugin_id="waiter")
    check("依赖缺失时挂起", ctx._plugins["waiter"].status == "pending")
    ctx.provide("later", _Svc())
    check("服务出现后自动激活", ctx._plugins["waiter"].status == "active")
    check("激活时服务已可用", order == ["active:_Svc"])


def test_events() -> None:
    print("== 事件五模式 ==")
    ctx = Context("t-events")
    events: list[str] = []
    ctx.on("ping", lambda x: events.append(f"on:{x}"))
    ctx.once("ping", lambda x: events.append(f"once:{x}"))
    ctx.emit("ping", 1)
    ctx.emit("ping", 2)
    check("on 多次 + once 单次", events == ["on:1", "once:1", "on:2"])
    ctx.on("calc", lambda v, add: v + add)
    ctx.on("calc", lambda v, add: v * add)
    check("waterfall 逐级传递", ctx.waterfall("calc", 1, 2) == 6)
    ctx.on("bail", lambda x: None)
    ctx.on("bail", lambda x: f"hit:{x}")
    check("bail 短路第一个非 None", ctx.bail("bail", 7) == "hit:7")
    check("emit 空事件返回 []", ctx.emit("nope") == [])


def test_disposers() -> None:
    print("== disposer 逆序回收 ==")
    ctx = Context("t-disp")
    disposed: list[str] = []

    class P:
        def apply(self, ctx, config):
            ctx.effect(lambda: disposed.append("a"), label="a")
            ctx.effect(lambda: disposed.append("b"), label="b")

    dp = ctx.plugin(P(), plugin_id="p")
    check("未卸载时未回收", disposed == [])
    dp()
    check("卸载逆序回收", disposed == ["b", "a"])
    check("重复 dispose 幂等", dp() is None)


def test_timer() -> None:
    print("== 定时器 ==")
    ctx = Context("t-timer")
    ticks: list[int] = []

    class P:
        def apply(self, ctx, config):
            ctx.set_interval(lambda: ticks.append(1), 0.05, label="tick")

    dp = ctx.plugin(P(), plugin_id="p")
    time.sleep(0.12)
    check("interval 运行", len(ticks) >= 2)
    dp()
    n_stopped = len(ticks)
    time.sleep(0.12)
    check("卸载后停止", len(ticks) == n_stopped)


def test_composition_and_boot() -> None:
    print("== 组合加载与标准装配 ==")
    from agent_core.cordis.boot import get_app_context
    import agent_core.cordis.boot as boot

    boot._app_ctx = None
    ctx = get_app_context()
    snap = ctx.snapshot()
    check("标准服务已注册（lessons/subagents/llm/trace_audit）",
          {"lessons", "subagents", "llm", "trace_audit"} <= set(snap["services"]))
    check("组合插件 active（subagent_cleaner）",
          snap["plugins"].get("agent_core.cordis_plugins.subagent_cleaner") == "active")
    ctx.stop()
    check("stop 全量卸载", all(f.status == "disposed" for f in ctx._plugins.values()))


def main() -> None:
    test_services()
    test_inject_activation()
    test_events()
    test_disposers()
    test_timer()
    test_composition_and_boot()
    print(f"\n结果: {PASS} 通过, {FAIL} 失败")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
