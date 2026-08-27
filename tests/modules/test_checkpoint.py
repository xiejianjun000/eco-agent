"""会话检查点/回滚：快照/列举/回滚/多会话隔离/损坏快照容错（全 mock，离线）。"""
import json

import pytest

from agent_core.checkpoint import CheckpointStore, _decisions_count
from agent_core.workspace import WorkspaceManager
from eco.commands import cmd_chat


@pytest.fixture()
def cp_root(tmp_path):
    return tmp_path / "checkpoints"


@pytest.fixture()
def store(cp_root):
    return CheckpointStore(session="s1", root=cp_root)


@pytest.fixture()
def ws_manager(tmp_path, monkeypatch):
    mgr = WorkspaceManager(tmp_path / "workspaces")
    monkeypatch.setattr("agent_core.workspace._manager", mgr)
    yield mgr
    monkeypatch.setattr("agent_core.workspace._manager", None)


def _mk_ws(mgr, name="合力砖厂检查"):
    ws = mgr.create(name)
    mgr.open(ws.meta["slug"])
    return ws


class TestCheckpointStore:
    def test_create_returns_snapshot_with_history(self, store):
        hist = [{"role": "user", "content": "查排污许可证"}]
        cp = store.create(history=hist)
        assert cp["id"] == 1
        assert cp["history"] == hist
        assert cp["session"] == "s1"

    def test_create_increments_id(self, store):
        store.create(history=[])
        cp2 = store.create(history=[])
        assert cp2["id"] == 2

    def test_create_persists_to_disk(self, store):
        store.create(history=[{"role": "user", "content": "x"}])
        files = list(store.dir.glob("*.json"))
        assert len(files) == 1
        data = json.loads(files[0].read_text(encoding="utf-8"))
        assert data["history"][0]["content"] == "x"

    def test_list_empty(self, store):
        assert store.list() == []

    def test_list_sorted(self, store):
        for i in range(3):
            store.create(history=[{"role": "user", "content": f"q{i}"}])
        cps = store.list()
        assert [c["id"] for c in cps] == [1, 2, 3]

    def test_workspace_files_snapshot(self, store, ws_manager):
        ws = _mk_ws(ws_manager)
        ws.append_note("现场发现暗管")
        cp = store.create(history=[], ws=ws)
        files = cp["workspace"]["files"]
        assert "notes.md" in files and "todos.md" in files and "meta.json" in files
        assert "暗管" in files["notes.md"]["content"]
        assert len(files["notes.md"]["sha256"]) == 64

    def test_rewind_restores_history(self, store):
        store.create(history=[{"role": "user", "content": "第一轮"}])
        store.create(history=[{"role": "user", "content": "第一轮"},
                              {"role": "assistant", "content": "答"},
                              {"role": "user", "content": "第二轮"}])
        cp = store.rewind(1)
        assert cp is not None
        assert cp["history"] == [{"role": "user", "content": "第一轮"}]

    def test_rewind_restores_workspace_files(self, store, ws_manager):
        ws = _mk_ws(ws_manager)
        ws.append_note("回滚前的笔记")
        store.create(history=[], ws=ws)
        ws.append_note("回滚后新增的笔记")
        ws.append_todo("回滚后的待办")
        cp = store.rewind(1, ws=ws)
        assert cp is not None
        assert "回滚前的笔记" in ws.notes()
        assert "回滚后新增的笔记" not in ws.notes()
        assert "回滚后的待办" not in ws.todos()

    def test_rewind_deletes_later_checkpoints(self, store):
        for _ in range(3):
            store.create(history=[])
        store.rewind(1)
        assert [c["id"] for c in store.list()] == [1]

    def test_rewind_nonexistent_returns_none(self, store):
        store.create(history=[])
        assert store.rewind(99) is None

    def test_corrupted_snapshot_skipped_in_list(self, store):
        store.create(history=[])
        bad = store.dir / "9999.json"
        bad.write_text("{not valid json!!!", encoding="utf-8")
        cps = store.list()
        assert len(cps) == 1  # 损坏快照被跳过

    def test_corrupted_target_rewind_returns_none(self, store):
        bad = store.dir / "0005.json"
        bad.write_text("garbage", encoding="utf-8")
        assert store.rewind(5) is None

    def test_multi_session_isolation(self, cp_root):
        s1 = CheckpointStore(session="alpha", root=cp_root)
        s2 = CheckpointStore(session="beta", root=cp_root)
        s1.create(history=[{"role": "user", "content": "alpha"}])
        s2.create(history=[{"role": "user", "content": "beta"}])
        assert len(s1.list()) == 1 and len(s2.list()) == 1
        assert s1.list()[0]["history"][0]["content"] == "alpha"
        # alpha 回滚不影响 beta
        s1.rewind(1)
        assert len(s2.list()) == 1

    def test_decisions_count_recorded(self, store, tmp_path):
        df = tmp_path / "decisions.jsonl"
        df.write_text('{"a":1}\n{"b":2}\n', encoding="utf-8")
        cp = store.create(history=[], decisions_file=df)
        assert cp["decisions_count"] == 2

    def test_decisions_count_missing_file(self, tmp_path):
        assert _decisions_count(tmp_path / "nope.jsonl") == 0


class TestReplCommands:
    """REPL 层：/checkpoints、/rewind 与自动快照（input/print 打桩）。"""

    def _run_repl(self, monkeypatch, inputs):
        it = iter(inputs + ["/exit"])
        monkeypatch.setattr("builtins.input", lambda prompt="": next(it))
        lines = []
        monkeypatch.setattr("builtins.print", lambda *a, **k: lines.append(" ".join(map(str, a))))
        monkeypatch.setattr(cmd_chat, "_HAVE_RICH", False)
        # 用户问题会走 LLM，直接打桩掉
        monkeypatch.setattr(cmd_chat, "_maybe_swarm", lambda *a, **k: "模拟回答")
        cmd_chat._repl(history=[])
        return "\n".join(lines)

    def test_checkpoints_empty(self, ws_manager, monkeypatch, tmp_path):
        monkeypatch.setattr("agent_core.checkpoint.CP_ROOT", tmp_path / "cp")
        out = self._run_repl(monkeypatch, ["/checkpoints"])
        assert "暂无检查点" in out

    def test_auto_snapshot_before_input(self, ws_manager, monkeypatch, tmp_path):
        cp_root = tmp_path / "cp"
        monkeypatch.setattr("agent_core.checkpoint.CP_ROOT", cp_root)
        self._run_repl(monkeypatch, ["查一下排污许可证"])
        store = CheckpointStore(session="default", root=cp_root)
        cps = store.list()
        assert len(cps) == 1  # 用户输入前自动快照
        assert cps[0]["history"] == []

    def test_checkpoints_lists_snapshots(self, ws_manager, monkeypatch, tmp_path):
        monkeypatch.setattr("agent_core.checkpoint.CP_ROOT", tmp_path / "cp")
        out = self._run_repl(monkeypatch, ["问题一", "/checkpoints"])
        assert "#1" in out

    def test_rewind_truncates_history(self, ws_manager, monkeypatch, tmp_path):
        monkeypatch.setattr("agent_core.checkpoint.CP_ROOT", tmp_path / "cp")
        # 第一轮快照(空历史) -> 第一轮回答 -> 第二轮快照(2条) -> 第二轮回答 -> rewind 到 #1
        out = self._run_repl(monkeypatch, ["问题一", "问题二", "/rewind 1"])
        assert "已回滚到检查点 #1" in out
        assert "会话历史 0 条" in out

    def test_rewind_default_latest(self, ws_manager, monkeypatch, tmp_path):
        monkeypatch.setattr("agent_core.checkpoint.CP_ROOT", tmp_path / "cp")
        out = self._run_repl(monkeypatch, ["问题一", "/rewind"])
        assert "已回滚到检查点 #1" in out

    def test_rewind_invalid_arg(self, ws_manager, monkeypatch, tmp_path):
        monkeypatch.setattr("agent_core.checkpoint.CP_ROOT", tmp_path / "cp")
        out = self._run_repl(monkeypatch, ["问题一", "/rewind abc"])
        assert "无效检查点编号" in out

    def test_rewind_no_checkpoint(self, ws_manager, monkeypatch, tmp_path):
        monkeypatch.setattr("agent_core.checkpoint.CP_ROOT", tmp_path / "cp")
        out = self._run_repl(monkeypatch, ["/rewind"])
        assert "无可回滚的检查点" in out

    def test_rewind_nonexistent_id(self, ws_manager, monkeypatch, tmp_path):
        monkeypatch.setattr("agent_core.checkpoint.CP_ROOT", tmp_path / "cp")
        out = self._run_repl(monkeypatch, ["问题一", "/rewind 42"])
        assert "不存在" in out

    def test_help_mentions_rewind(self):
        assert "/rewind" in cmd_chat._HELP_TEXT
        assert "/checkpoints" in cmd_chat._HELP_TEXT
