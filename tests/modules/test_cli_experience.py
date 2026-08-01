"""CLI 体验测试：/help 命令清单、启动横幅摘要、eco trace 命令"""

from agent_core.observability import SpanTree
from eco.commands import cmd_chat, cmd_trace


class TestHelpAndBanner:
    def test_help_lists_all_repl_commands(self):
        for cmd in ("/help", "/exit", "/new", "/ws", "/todo", "/verbose"):
            assert cmd in cmd_chat._HELP_TEXT

    def test_banner_summary_line(self):
        line = cmd_chat._banner_summary()
        assert "provider/model" in line
        assert "workspace" in line
        assert "权限闸门" in line

    def test_model_command_text(self):
        out = cmd_chat._model_cmd_text("")
        assert "[model] 当前" in out and "deepseek" in out
        assert "eco config model use" in out
        bad = cmd_chat._model_cmd_text("no_such_provider")
        assert "未知 provider" in bad

    def test_self_system_extra_facts(self):
        info = cmd_chat._self_system_extra()
        assert "自述信息" in info and "/model" in info
        assert "eco config model use" in info

    def test_status_bar_format(self):
        bar = cmd_chat._status_bar([{"role": "user", "content": "你好 eco"}])
        assert "context:" in bar
        assert "gate:" in bar and ("gate:on" in bar or "gate:off" in bar)
        assert cmd_chat._context_status([]).startswith("context: 0%")
        # 长会话逼近上限时不应超过 100%
        huge = [{"role": "user", "content": "x" * 4 * 200000}]
        assert "100%" in cmd_chat._context_status(huge)


class TestTraceCommand:
    class Args:
        def __init__(self, session=None, tree=False, otel=None):
            self.session = session
            self.tree = tree
            self.otel = otel

    def _make_session(self, tmp_path, monkeypatch):
        monkeypatch.setattr("agent_core.observability.TRACES_DIR", tmp_path)
        monkeypatch.setattr("eco.commands.cmd_trace.TRACES_DIR", tmp_path)
        tree = SpanTree()
        root = tree.start("chat", "session")
        llm = tree.start("round1", "llm_call", model="deepseek-chat")
        t = tree.start("save_document", "tool_call", args={"f": 1})
        tree.end(t, result="ok")
        tree.end(llm, finish_reason="stop", prompt_tokens=5, completion_tokens=3)
        tree.end(root)
        tree.save()
        return tree

    def test_list_sessions(self, tmp_path, monkeypatch, capsys):
        tree = self._make_session(tmp_path, monkeypatch)
        assert cmd_trace.run(self.Args()) == 0
        out = capsys.readouterr().out
        assert tree.session_id in out

    def test_tree_render(self, tmp_path, monkeypatch, capsys):
        tree = self._make_session(tmp_path, monkeypatch)
        assert cmd_trace.run(self.Args(session=tree.session_id, tree=True)) == 0
        out = capsys.readouterr().out
        assert "llm_call:round1" in out
        assert "tool_call:save_document" in out
        assert "└─" in out

    def test_otlp_export(self, tmp_path, monkeypatch, capsys):
        tree = self._make_session(tmp_path, monkeypatch)
        out_path = tmp_path / "out.otlp.json"
        assert cmd_trace.run(self.Args(session=tree.session_id, tree=True,
                                       otel=str(out_path))) == 0
        assert out_path.exists()
        import json
        data = json.loads(out_path.read_text(encoding="utf-8"))
        assert data["resourceSpans"][0]["scopeSpans"][0]["spans"]
        assert "OTLP" in capsys.readouterr().out

    def test_missing_session(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr("agent_core.observability.TRACES_DIR", tmp_path)
        monkeypatch.setattr("eco.commands.cmd_trace.TRACES_DIR", tmp_path)
        assert cmd_trace.run(self.Args(session="nope")) == 1
        assert "未找到" in capsys.readouterr().out
