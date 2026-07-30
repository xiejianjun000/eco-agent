# -*- coding: utf-8 -*-
"""会话恢复：eco chat --continue / --resume <slug> 从 history.jsonl 重建 history。"""
import argparse

import pytest

from agent_core.workspace import WorkspaceManager
from eco.commands import cmd_chat


@pytest.fixture()
def ws_manager(tmp_path, monkeypatch):
    mgr = WorkspaceManager(tmp_path)
    monkeypatch.setattr("agent_core.workspace._manager", mgr)
    yield mgr
    monkeypatch.setattr("agent_core.workspace._manager", None)


def _two_turn_session(mgr, name="合力砖厂检查"):
    """模拟一轮两轮会话：创建/打开工作区并写入两条用户+助手事件。"""
    ws = mgr.create(name)
    mgr.open(ws.meta["slug"])
    ws.add_event("user", "第一轮：查合力砖厂排污许可证")
    ws.add_event("assistant", "已查到许可证编号 XS-2024-001")
    ws.add_event("user", "第一轮追加：有效期到什么时候")
    ws.add_event("assistant", "有效期至 2026-12-31")
    return ws


class TestSessionRestore:
    def test_continue_restores_most_recent(self, ws_manager):
        _two_turn_session(ws_manager, "合力砖厂检查")
        _two_turn_session(ws_manager, "宏远水泥核查")
        args = argparse.Namespace(continue_session=True, resume=None)
        history = cmd_chat._restore_session(args)
        # 最近活跃为第二个工作区
        assert len(history) == 4
        assert "宏远" in str(ws_manager.current().meta.get("name"))

    def test_continue_after_first_session_contains_first_round(self, ws_manager):
        ws = _two_turn_session(ws_manager)
        ws_manager.close()  # 模拟进程退出
        args = argparse.Namespace(continue_session=True, resume=None)
        history = cmd_chat._restore_session(args)
        # 第二轮会话（恢复后）消息中应包含第一轮内容
        assert history[0] == {"role": "user", "content": "第一轮：查合力砖厂排污许可证"}
        assert history[1]["role"] == "assistant"
        assert "XS-2024-001" in history[1]["content"]
        assert any("2026-12-31" in m["content"] for m in history)
        # 且工作区被重新打开
        assert ws_manager.current_name() == ws.meta["slug"]

    def test_resume_by_slug(self, ws_manager):
        ws = _two_turn_session(ws_manager)
        ws_manager.close()
        args = argparse.Namespace(continue_session=False, resume=ws.meta["slug"])
        history = cmd_chat._restore_session(args)
        assert len(history) == 4
        assert ws_manager.current_name() == ws.meta["slug"]

    def test_resume_missing_workspace(self, ws_manager, capsys):
        args = argparse.Namespace(continue_session=False, resume="不存在的工作区")
        assert cmd_chat._restore_session(args) == []
        assert "未找到工作区" in capsys.readouterr().out

    def test_no_flags_returns_empty(self, ws_manager):
        args = argparse.Namespace(continue_session=False, resume=None)
        assert cmd_chat._restore_session(args) == []

    def test_restored_history_feeds_messages(self, ws_manager):
        """恢复的 history 进入 _build_messages，第二轮请求携带第一轮内容。"""
        _two_turn_session(ws_manager)
        args = argparse.Namespace(continue_session=True, resume=None)
        history = cmd_chat._restore_session(args)
        msgs = cmd_chat._build_messages(history, "第二轮：继续分析")
        roles = [m["role"] for m in msgs]
        assert roles[0] == "system" and roles[-1] == "user"
        assert "第一轮：查合力砖厂排污许可证" in [m["content"] for m in msgs]
