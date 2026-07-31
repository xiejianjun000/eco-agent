#!/usr/bin/env python3
"""workspace 项目工作区测试（LLM 层不涉及）"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest
from agent_core.workspace import WorkspaceManager, slugify
from agent_core.prompt_engine import PromptEngine, PromptAuditChain


@pytest.fixture()
def mgr(tmp_path):
    return WorkspaceManager(root=tmp_path / "workspaces")


class TestWorkspaceCRUD:
    def test_create_and_get(self, mgr):
        ws = mgr.create("合力砖厂")
        assert ws.path.is_dir()
        for f in ("meta.json", "notes.md", "history.jsonl", "todos.md"):
            assert (ws.path / f).exists()
        assert ws.meta["name"] == "合力砖厂"
        assert mgr.get("合力砖厂").path == ws.path
        with pytest.raises(FileExistsError):
            mgr.create("合力砖厂")

    def test_list_and_open_close(self, mgr):
        mgr.create("合力砖厂")
        mgr.create("光明水泥厂")
        assert len(mgr.list()) == 2
        assert mgr.current() is None
        assert mgr.open("合力砖厂") is not None
        assert mgr.current_name() == "合力砖厂"
        assert mgr.close() == "合力砖厂"
        assert mgr.current() is None

    def test_open_unknown_returns_none(self, mgr):
        assert mgr.open("不存在的厂") is None

    def test_slugify_safe(self):
        assert slugify(" 合力 砖厂/A:B ") == "合力-砖厂-A-B"
        assert slugify("") .startswith("ws-")

    def test_events_notes_todos_summary(self, mgr):
        ws = mgr.create("合力砖厂")
        ws.add_event("user", "检查脱硫设施")
        ws.add_event("assistant", "已核查脱硫设施运行台账")
        ws.add_event("law", "《大气污染防治法》第二十条")
        ws.append_todo("复查在线监测数据")
        ws.append_note("现场发现台账不全")
        m = ws.meta
        m["correction_refs"] = ["不对，应该是大气法第四十五条"]
        ws._save_meta(m)
        s = ws.summary()
        assert "合力砖厂" in s
        assert "检查脱硫设施" in s
        assert "大气污染防治法" in s
        assert "复查在线监测数据" in s
        assert "第四十五条" in s
        assert len(ws.history()) == 3


class TestResumeIntent:
    def test_resume_by_name(self, mgr):
        mgr.create("合力砖厂")
        ws = mgr.detect_resume_intent("继续上次合力砖厂的检查")
        assert ws is not None and ws.meta["name"] == "合力砖厂"

    def test_resume_latest_when_unnamed(self, mgr):
        mgr.create("甲厂")
        b = mgr.create("乙厂")
        b.touch()
        ws = mgr.detect_resume_intent("继续上次的检查")
        assert ws is not None

    def test_no_intent(self, mgr):
        mgr.create("合力砖厂")
        assert mgr.detect_resume_intent("大气法第二十条内容是什么") is None
        assert mgr.detect_resume_intent("") is None


class TestPromptInjection:
    def test_summary_injected_via_engine(self, mgr, tmp_path):
        ws = mgr.create("合力砖厂")
        ws.add_event("user", "检查脱硫设施")
        mgr.open("合力砖厂")
        eng = PromptEngine(audit_chain=PromptAuditChain(tmp_path / "audit.jsonl"))
        assert mgr.inject_current_summary(engine=eng) is True
        prompt = eng.build_system_prompt()
        assert "合力砖厂" in prompt
        assert prompt.startswith("【安全准则")
        # 审计链有记录
        assert eng.audit.verify_chain()["valid"] is True

    def test_no_active_workspace_no_injection(self, mgr, tmp_path):
        eng = PromptEngine(audit_chain=PromptAuditChain(tmp_path / "audit.jsonl"))
        assert mgr.inject_current_summary(engine=eng) is False
        assert eng.list_injections() == []


class TestMemoryTreeFreeze:
    def test_freeze(self, mgr, tmp_path):
        ws = mgr.create("合力砖厂")
        ws.add_event("user", "全套大气检查")
        r = mgr.freeze_to_memory_tree(ws, db_path=tmp_path / "mem.db")
        assert r["ok"] is True
        # 可检索
        from _scripts.memory_tree import MemoryTree
        mt = MemoryTree(db_path=tmp_path / "mem.db")
        hits = mt.search("合力砖厂")
        assert hits
