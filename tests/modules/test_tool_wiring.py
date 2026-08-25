"""接线清单回归：聊天通道必须包含 WIRED_REQUIRED 全部工具，
且聊天清单里的每个工具都必须有真实 handler——防止"注册了但没接线"类缺口。"""


def test_wired_required_in_chat():
    from agent_core.wiring_manifest import WIRED_REQUIRED
    from server.api.chat import _codex_tools

    wired = {t["function"]["name"] for t in _codex_tools()}
    missing = [n for n in WIRED_REQUIRED if n not in wired]
    assert not missing, f"接线清单缺口（有实现但未接聊天通道）: {missing}"


def test_chat_tools_have_handlers():
    from agent_core.tools_registry import _HANDLERS, resolve_tool_name
    from agent_core.wiring_manifest import CHANNEL_DISPATCHED
    from server.api.chat import _codex_tools

    wired = {t["function"]["name"] for t in _codex_tools()}
    no_handler = [
        n for n in wired
        if n not in CHANNEL_DISPATCHED
        and n not in _HANDLERS and resolve_tool_name(n) not in _HANDLERS
    ]
    assert not no_handler, f"聊天清单里的工具没有实现 handler: {no_handler}"
