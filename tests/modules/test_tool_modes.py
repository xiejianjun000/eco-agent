"""模式级工具白名单测试（对标 WorkBuddy interactionmode 工具策略）。

WorkBuddy 实测：ask 模式 10 个只读工具（无 Write/无 Bash），craft 37 个全能力。
eco 此前一次性给出全部 44 个工具，纯问答场景也拿到 shell 与写文件。
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from server.api.chat import (  # noqa: E402
    _MUTATING_TOOLS,
    _chat_tool_list,
    _is_readonly_request,
)


def _names(readonly: bool) -> set[str]:
    return {d["function"]["name"] for d in _chat_tool_list(readonly=readonly)}


def test_readonly_excludes_all_mutating_tools():
    """只读模式绝不能出现任何写入/执行工具 —— 这是安全边界。"""
    ro = _names(readonly=True)
    leaked = ro & _MUTATING_TOOLS
    assert not leaked, f"只读模式泄露了写入工具: {sorted(leaked)}"


def test_readonly_keeps_query_tools():
    """只读模式仍要能查：检索/读文件/审计链必须在。"""
    ro = _names(readonly=True)
    for must in ("file_read", "glob", "grep", "audit_tail", "inspect"):
        assert must in ro, f"只读模式缺少必要查询工具 {must}"


def test_full_mode_is_superset():
    """全能力模式必须是只读模式的超集，且确实更多。"""
    ro, full = _names(readonly=True), _names(readonly=False)
    assert ro < full, "只读集合应严格小于全量集合"
    assert _MUTATING_TOOLS <= full, "全能力模式应包含全部写入工具"


def test_mcp_tools_survive_readonly():
    """MCP 工具是外部只读查询，不应被误杀（若当前有挂载）。"""
    full = _names(readonly=False)
    mcp_full = {n for n in full if n.startswith("mcp__")}
    if not mcp_full:
        return  # 当前无 MCP 挂载，跳过
    ro = _names(readonly=True)
    assert {n for n in ro if n.startswith("mcp__")} == mcp_full


def test_intent_detection():
    """意图判定：写入意图一律给全能力，纯查询才降权。"""
    # 纯查询 → 只读
    for q in ("查一下审计链最后 3 条", "看看有多少个工具", "读 README 前 10 行",
              "统计一下文件数", "哪些 MCP 挂载了", "为什么会卡住"):
        assert _is_readonly_request(q) is True, f"应判定为只读: {q}"

    # 含写入/执行意图 → 全能力（宁可放过不可错杀）
    for q in ("查一下配置然后改掉", "读 README 并生成一份摘要文档",
              "跑一下测试", "查审计链并画个图", "看看日志，修复报错",
              "统计文件数并写入报告"):
        assert _is_readonly_request(q) is False, f"应判定为全能力: {q}"

    # 空输入不降权
    assert _is_readonly_request("") is False


def test_mcp_write_tools_blocked_in_readonly():
    """MCP 写工具必须被拦住。

    腾讯文档 MCP 单独挂了 100+ 个工具，其中 insert_/delete_/set_/update_
    全是写操作。只按内置白名单过滤时实测仍放行了全部 MCP 写工具
    （115→91，写权限几乎没减）——必须按动词判断。
    """
    ro = _names(readonly=True)
    write_like = [
        n for n in ro
        if n.startswith("mcp__")
        and any(v in n.split("__", 2)[-1].lower()
                for v in ("insert", "delete", "set_", "update", "create",
                          "remove", "write", "replace", "rename"))
    ]
    assert not write_like, f"只读模式残留 MCP 写工具: {write_like[:8]}"


def test_mcp_readonly_tools_survive():
    """MCP 的只读查询工具不能被误杀。"""
    full = _names(readonly=False)
    if not any(n.startswith("mcp__") for n in full):
        return
    ro = _names(readonly=True)
    kept = [n for n in ro if n.startswith("mcp__")]
    assert kept, "所有 MCP 工具都被误杀了"
    # 明确的只读动词必须留下
    for verb in ("get_", "query_", "read_", "list_"):
        if any(verb in n.split("__", 2)[-1].lower() for n in full if n.startswith("mcp__")):
            assert any(verb in n.split("__", 2)[-1].lower() for n in kept), \
                f"只读动词 {verb} 的 MCP 工具被误杀"


def test_tool_is_readonly_unit():
    """_tool_is_readonly 逐项判定。"""
    from server.api.chat import _tool_is_readonly
    assert _tool_is_readonly("file_read") is True
    assert _tool_is_readonly("file_write") is False
    assert _tool_is_readonly("shell_run") is False
    assert _tool_is_readonly("mcp__tencent_docs__doc_get_outline") is True
    assert _tool_is_readonly("mcp__tencent_docs__doc_insert_text") is False
    assert _tool_is_readonly("mcp__tencent_docs__sheet_set_cell_value") is False
    assert _tool_is_readonly("mcp__eco-hunan-env__read_air_quality") is True
    assert _tool_is_readonly("") is False
    # 未登记的内置工具默认不给（保守）
    assert _tool_is_readonly("some_unknown_tool") is False
