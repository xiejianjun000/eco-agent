"""安全门禁：确定性本地断言（无网络、无 LLM）。quality-gate 门禁 1-5 安全相关快速检查。"""

from agent_core import eco_notepad, eco_state, schema_guard


def test_schema_guard_bool_vs_number():
    """schema 层类型判定：bool 必须是 boolean，不能误入 number。"""
    schema = {"type": "object", "properties": {"flag": {"type": "boolean"}}, "required": ["flag"]}
    ok, _ = schema_guard.SchemaGuard.validate({"flag": True}, schema)
    assert ok is True
    ok2, _ = schema_guard.SchemaGuard.validate({"flag": 1}, schema)
    assert ok2 is False


def test_notepad_archive_idempotent(tmp_path):
    """notepad archive 幂等：按 add 返回 id 归档，重复归档返回 False。"""
    store = eco_notepad.NotepadStore(str(tmp_path / ".eco"))
    rec = store.add("t1", "hello secret", kind="note")
    note_id = rec["id"]
    assert store.archive(note_id) is True
    assert store.archive(note_id) is False


def test_eco_state_list_summary(tmp_path):
    """state registry list/summary 在隔离 HOME 下不抛错。"""
    reg = eco_state.EcoStateRegistry(eco_root=tmp_path / "eco", home_root=tmp_path / "home")
    entries = reg.list()
    summary = reg.summary()
    assert isinstance(entries, list)
    assert isinstance(summary, dict)


def test_import_core_modules():
    """核心模块导入不抛错（无 key 兜底路径）。"""
    for name in [
        "schema_guard",
        "cost_ledger",
        "eco_peer",
        "mcp_registry",
        "eco_state",
        "eco_notepad",
        "eco_monitor",
        "browser_tool",
    ]:
        __import__(f"agent_core.{name}")
