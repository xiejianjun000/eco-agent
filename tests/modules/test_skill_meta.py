#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""元技能三件套 + P0 评测集地基回归测试
========================================
覆盖：meta-audit 自审评分、meta-test 用例生成、meta-interview 批量骨架、
run_evals 机械校验（含 mock 法典库查询）。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402


def _load_script(rel_path: str):
    """按路径加载 ecoskills 下无包的脚本模块（测试用）。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        rel_path.replace("/", "_").replace(".py", ""), str(ROOT / rel_path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── 1. meta-audit ────────────────────────────────────────────────

def test_audit_atom_skills_pass(tmp_path, monkeypatch):
    audit_mod = _load_script("ecoskills/meta-audit/scripts/audit.py")

    monkeypatch.setattr(audit_mod, "SKILLS_DIR", ROOT / "ecoskills")
    for name in ("atom-constitutive", "atom-evidence-chain", "atom-discretion"):
        r = audit_mod.audit_skill(name)
        assert r["exists"] and r["pass"], f"{name} 自审应 ≥70: {r['score']}"
        assert r["score"] >= 90, f"{name} 评分异常: {r['score']}"


def test_audit_detects_bad_skill(tmp_path, monkeypatch):
    audit_mod = _load_script("ecoskills/meta-audit/scripts/audit.py")

    skills = tmp_path / "ecoskills"
    (skills / "bad-skill").mkdir(parents=True)
    (skills / "bad-skill" / "SKILL.md").write_text("---\n---\n正文太短", encoding="utf-8")
    monkeypatch.setattr(audit_mod, "SKILLS_DIR", skills)
    r = audit_mod.audit_skill("bad-skill")
    assert not r["pass"]
    assert r["score"] < 70


# ── 2. meta-test ────────────────────────────────────────────────

def test_meta_test_generates_cases(tmp_path, monkeypatch):
    test_mod = _load_script("ecoskills/meta-test/scripts/test.py")

    monkeypatch.setattr(test_mod, "EVALS_DIR", tmp_path)
    result = test_mod.generate_cases("atom-discretion")
    out = Path(result["out"])
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert result["cases"] >= 5, f"用例数过少: {result['cases']}"
    assert "黄金要点" in text and "维度" in text


def test_meta_test_citation_articles_extracted(tmp_path, monkeypatch):
    test_mod = _load_script("ecoskills/meta-test/scripts/test.py")

    monkeypatch.setattr(test_mod, "EVALS_DIR", tmp_path)
    test_mod.generate_cases("atom-constitutive")
    text = (tmp_path / "atom-constitutive-cases.md").read_text(encoding="utf-8")
    assert "## Q" in text


# ── 3. meta-interview ───────────────────────────────────────────

def test_interview_batch_mode(tmp_path, monkeypatch):
    import json

    iv_mod = _load_script("ecoskills/meta-interview/scripts/interview.py")

    monkeypatch.setattr(iv_mod, "SKILLS_DIR", tmp_path)
    answers = {
        "q1": "现场检查笔录制作",
        "q2": "写现场检查笔录、笔录要素、笔录模板",
        "q3": "Step 1: 记录现场；Step 2: 签认",
        "q4": "签认时限、见证人要求",
        "q5": "漏记当事人陈述；漏签认",
        "q6": "不得虚构检查事实",
        "q7": "【笔录结构】检查信息/现场情况/签认",
        "q8": "模板目录",
    }
    answers_file = tmp_path / "answers.json"
    answers_file.write_text(json.dumps(answers, ensure_ascii=False), encoding="utf-8")

    skill_dir = tmp_path / "scene-demo"
    skill_dir.mkdir()
    out = skill_dir / "SKILL.md"
    out.write_text(iv_mod._build_skill("scene-demo", answers), encoding="utf-8")

    text = out.read_text(encoding="utf-8")
    assert "name: scene-demo" in text
    assert "触发词：" in text
    assert "Step 1" in text and "禁用领域" in text and "输出格式" in text


# ── 4. run_evals 机械校验 ───────────────────────────────────────

def test_evals_suites_parse():
    from _scripts.run_evals import parse_suite

    for name, min_q in (("statute-application", 4), ("case-review", 7),
                        ("document-drafting", 4)):
        qs = parse_suite(ROOT / "evals" / f"{name}.md")
        assert len(qs) >= min_q, f"{name} 题目数不足: {len(qs)}"
        assert all(q["question"] and q["golden"] for q in qs)


def test_mechanical_article_check_mock(monkeypatch):
    import _scripts.run_evals as ev

    fake = ROOT / "evals" / "statute-application.md"  # 真实存在（用作 path= 校验）
    ok, note = ev.mechanical_check(
        {"citation": "article=164", "question": "", "dimension": "", "golden": ""})
    assert ok and "命中" in note  # 真实法典库校验（164 条存在）
    ok2, _ = ev.mechanical_check(
        {"citation": f"path=evals/statute-application.md", "question": "",
         "dimension": "", "golden": ""})
    assert ok2
    ok3, note3 = ev.mechanical_check(
        {"citation": "article=999999", "question": "", "dimension": "", "golden": ""})
    assert not ok3


def test_mechanical_report_shape():
    from _scripts.run_evals import run_mechanical

    report = run_mechanical([ROOT / "evals" / "statute-application.md"])
    assert report["total"] == 5
    assert report["passed"] == 5  # 4 条 article 校验 + 1 skip
    assert report["failed"] == []


def test_scene_skills_pass_audit():
    """第一批场景技能（现场笔录/处罚告知/案卷评查）自审 ≥70。"""
    audit_mod = _load_script("ecoskills/meta-audit/scripts/audit.py")
    for name in ("scene-jcbl", "scene-cfzz", "scene-ajpc"):
        r = audit_mod.audit_skill(name)
        assert r["exists"] and r["pass"], f"{name} 应 ≥70: {r['score']}"


def test_scene_skills_discovered_by_registry():
    from agent_core.skill_dir import get_skill_dir_registry

    names = {s.get("name") for s in get_skill_dir_registry().list()}
    assert {"scene-jcbl", "scene-cfzz", "scene-ajpc"} <= names
