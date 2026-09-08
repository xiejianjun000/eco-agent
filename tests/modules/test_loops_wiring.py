#!/usr/bin/env python3
"""tests/modules/test_loops_wiring.py — 五层循环接线回归

背景（两个真实缺陷，均为「命名对不上导致代码路径永不执行」）：

  1) eco_loops_integration.py 原先 `from agent_core.self_healing import SelfHealing`，
     而该模块顶层只导出 `SelfHealer`。于是 except ImportError 恒成立、
     _HAS_SELF_HEALING 恒为 False、self.l5 恒为 None ——
     L5 自愈在集成层从未被加载过，get_stats() 里的 l5_healing 恒报 false。

  2) eco/commands/cmd_serve.py 原先 `import EcoLoops`，而模块只导出
     `EcoLoopsIntegration` 与实例 `loops`。该 ImportError 被外层
     `except Exception` 吞掉，cmd_serve 路径的循环启动静默失效。

这类缺陷的共同特征：语法正确、import 被 try/except 包着、日志不报错，
只有真正去调用才会暴露。本文件用「能否真的构造出来并跑一次」来锁死接线。
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


# ── 1. 模块导出名与导入名必须一致 ────────────────────────────────
def test_self_healing_exports_the_name_integration_imports():
    """self_healing 的顶层导出必须包含集成层实际 import 的名字。"""
    src = (ROOT / "agent_core" / "self_healing.py").read_text(encoding="utf-8")
    exported = {n.name for n in ast.parse(src).body
                if isinstance(n, (ast.ClassDef, ast.FunctionDef))}
    assert "SelfHealer" in exported, f"self_healing 顶层导出: {exported}"

    integ = (ROOT / "agent_core" / "eco_loops_integration.py").read_text(encoding="utf-8")
    assert "import SelfHealer" in integ, "集成层未导入真实存在的 SelfHealer"
    assert "import SelfHealing" not in integ, "集成层仍在导入不存在的 SelfHealing"


def test_cmd_serve_imports_a_name_that_exists():
    """cmd_serve 导入的循环类名必须真实存在于模块顶层。"""
    integ_src = (ROOT / "agent_core" / "eco_loops_integration.py").read_text(encoding="utf-8")
    exported = {n.name for n in ast.parse(integ_src).body
                if isinstance(n, (ast.ClassDef, ast.FunctionDef))}

    serve = (ROOT / "eco" / "commands" / "cmd_serve.py").read_text(encoding="utf-8")
    for line in serve.splitlines():
        if "eco_loops_integration import" in line:
            name = line.split("import")[-1].strip()
            assert name in exported, f"cmd_serve 导入了不存在的 {name}（模块导出 {exported}）"


# ── 2. L5 必须真的被加载（不是状态位说是就算）─────────────────────
def test_l5_is_actually_loaded():
    """_HAS_SELF_HEALING 为真，且 l5 是真实实例而非 None。"""
    import agent_core.eco_loops_integration as m

    assert m._HAS_SELF_HEALING is True, "L5 仍未加载（导入名可能又退化了）"
    assert m.loops.l5 is not None, "loops.l5 仍为 None"
    assert type(m.loops.l5).__name__ == "SelfHealer"


def test_get_stats_reports_l5_truthfully():
    """get_stats 的 l5_healing 必须如实反映加载结果。"""
    import agent_core.eco_loops_integration as m

    assert m.loops.get_stats().get("l5_healing") is True


# ── 3. 加载成功之后，它得真的能跑 ─────────────────────────────────
def test_protect_returns_result_on_success():
    """正常操作：success=True 且原样返回结果。"""
    from agent_core.self_healing import SelfHealer

    out = SelfHealer().protect(lambda: 42, context="unit-ok")
    assert out["success"] is True
    assert out["result"] == 42
    assert out["attempts"] >= 1


def test_protect_captures_failure_without_raising():
    """异常操作：捕获而不抛出，success=False 且带 error 描述。"""
    from agent_core.self_healing import SelfHealer

    out = SelfHealer().protect(lambda: 1 / 0, context="unit-div", max_retries=1)
    assert out["success"] is False
    assert "division by zero" in out["error"]


def test_protect_classifies_error_kinds():
    """失败分级：transient / permanent / deadlock / unknown 四类可区分。"""
    from agent_core.self_healing import SelfHealer

    h = SelfHealer()
    assert h._classify("connection reset by peer") == "transient"
    assert h._classify("404 not found") == "permanent"
    assert h._classify("deadlock detected") == "deadlock"
    assert h._classify("某种没见过的错") == "unknown"


def test_protect_uses_fallback_when_supplied():
    """fallback 降级：主操作失败时走兜底而非直接失败。"""
    from agent_core.self_healing import SelfHealer

    out = SelfHealer().protect(
        lambda: 1 / 0, context="unit-fb", fallback=lambda: "兜底值", max_retries=1)
    assert out.get("fallback") is True
    assert out.get("result") == "兜底值"


# ── 4. 诚实边界：能力可用 ≠ 已被使用 ──────────────────────────────
def test_protect_has_no_production_callsite_yet():
    """记录当前事实：protect() 尚无生产调用点。

    这不是缺陷断言，而是防止「l5_healing=true」被误读成
    「异常已被自动兜住」。等接入真实调用点后，本用例应随之更新
    （改为断言调用点存在），而不是被删掉。
    """
    hits: list[str] = []
    for sub in ("agent_core", "server", "gateway", "eco"):
        for py in (ROOT / sub).rglob("*.py"):
            if "test" in py.name or py.name == "self_healing.py":
                continue
            txt = py.read_text(encoding="utf-8", errors="replace")
            # 按 AST 找真实调用，避免把注释/文档里的 ".protect()" 误判为调用点
            try:
                tree = ast.parse(txt)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)
                        and node.func.attr == "protect"):
                    hits.append(str(py.relative_to(ROOT)))
                    break
    assert hits == [], (
        "protect() 已出现生产调用点，请把本用例改为断言调用点存在：" + ", ".join(hits))
