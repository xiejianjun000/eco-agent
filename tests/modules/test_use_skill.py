"""use_skill 工具测试（对标 WorkBuddy use_skill）。

背景：eco 有 54 个 SKILL.md，此前只有 eco-codex 被硬编码注入系统提示词，
其余 52 个模型既看不见也调不了 —— 全是死资产，包括
atom-constitutive（构成要件）、atom-discretion（裁量）、eia-review（环评审查）
这些执法核心能力。
"""
import asyncio
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))


def _call(args: dict) -> dict:
    from server.api.chat import _run_tool
    r = asyncio.run(_run_tool("use_skill", args))
    return json.loads(r)


def test_list_returns_skills():
    """list=true 应列出可用技能。"""
    d = _call({"list": True})
    assert d["ok"] is True
    assert d["count"] > 30, f"技能数异常: {d['count']}"
    names = {s["name"] for s in d["skills"]}
    for must in ("atom-constitutive", "atom-discretion", "eia-review", "fagui-query"):
        assert must in names, f"清单缺少核心技能 {must}"


def test_disable_model_invocation_hidden():
    """标记 disable-model-invocation 的不出现在清单里。"""
    d = _call({"list": True})
    assert "handoff" not in {s["name"] for s in d["skills"]}, \
        "handoff 标了 disable-model-invocation，不应出现在模型可见清单"


def test_disable_model_invocation_blocked():
    """即使直接点名，禁自调的技能也要拒绝。"""
    d = _call({"name": "handoff"})
    assert d["ok"] is False
    assert "禁止模型自主调用" in d["error"]


def test_load_real_skill():
    """加载真实技能应拿到正文。"""
    d = _call({"name": "atom-discretion"})
    assert d["ok"] is True
    assert d["name"] == "atom-discretion"
    assert len(d["content"]) > 200
    assert "裁量" in d["content"]


def test_unknown_skill_gives_hint():
    """技能不存在时要给出可用清单，而不是干瘪报错。"""
    d = _call({"name": "not-a-real-skill"})
    assert d["ok"] is False
    assert d["available"], "应返回可用技能清单"


def test_path_traversal_blocked():
    """防路径穿越：只取 basename。"""
    d = _call({"name": "../../../etc/passwd"})
    assert d["ok"] is False


def test_no_args_defaults_to_list():
    """不给参数时默认列清单，而不是报错。"""
    d = _call({})
    assert d["ok"] is True and d["count"] > 0
