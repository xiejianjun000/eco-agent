"""api_probe 端口解析 + inspect MCP 可见性测试。

真实事故（用户截图 + 轨迹 web-web_web-d3891360.json 复盘）：
  模型自检时探 /api/connectors → [Errno 61] Connection refused
  → 断言「没有单独运行的外部服务网关服务，所有外部服务工具已直接挂载」

  三处都错：
  1. api_probe 把 "/api/xxx" 拼到硬编码的 8000 端口，服务器实跑 8321，
     打到空端口自然拒绝 —— 探测工具自己给出了错误的失败信号
  2. 真实路由是 /api/v1/connectors，那里 14 台连接器全连、487 个工具
  3. 它手上的 inspect 清单只有 46 个工具、mcp__ 数为 0，
     却据此断言「MCP 都挂上了」—— 结论碰巧对，证据完全不支持
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))


def test_probe_no_hardcoded_8000():
    """默认端口不能写死 —— 这是 Connection refused 的根因。"""
    src = (REPO / "agent_core" / "exec_tools.py").read_text(encoding="utf-8")
    assert 'os.environ.get("ECO_PORT", "8000")' not in src, "仍在硬编码 8000"
    assert "_self_port()" in src, "应通过 _self_port() 解析端口"


def test_self_port_prefers_registered():
    """登记值优先于环境变量与兜底猜测。"""
    from agent_core import exec_tools as et
    old = et._SELF_PORT
    try:
        et.register_self_port(8321)
        assert et._self_port() == "8321"
        et.register_self_port("9999")
        assert et._self_port() == "9999"
    finally:
        et._SELF_PORT = old


def test_register_self_port_rejects_garbage():
    """非数字端口不能污染登记值。"""
    from agent_core import exec_tools as et
    old = et._SELF_PORT
    try:
        et.register_self_port(8321)
        et.register_self_port("not-a-port")
        assert et._SELF_PORT == "8321", "非法值不应覆盖已登记端口"
    finally:
        et._SELF_PORT = old


def test_app_registers_real_port():
    """server.run 必须把真实端口登记下去，否则简写又会打偏。"""
    src = (REPO / "server" / "app.py").read_text(encoding="utf-8")
    assert "register_self_port(port)" in src
    assert 'os.environ["ECO_PORT"] = str(port)' in src, "reload 子进程只能靠环境变量继承"


def test_inspect_triggers_mcp_attach():
    """inspect 查工具目录时必须确保 MCP 已挂载。

    此前是纯只读快照：MCP 还没挂就报 46 个、mcp__ 为 0，
    而对话通道实际有 128 个工具、82 个 MCP。自检报错误数字比不报更危险。
    """
    src = (REPO / "agent_core" / "inspect.py").read_text(encoding="utf-8")
    assert "attach_mcp_tools()" in src, "inspect 应触发挂载而非只读快照"


def test_inspect_sees_mcp_tools(monkeypatch):
    """list_tools() 必须把 ALL_TOOL_DEFS 里的 mcp__ 工具带出来。

    注意不能在单测里连真实 MCP：envboot.load_env_into_process() 见到
    PYTEST_CURRENT_TEST 会直接 return（刻意的环境隔离，防真实密钥污染单测），
    所以测试进程里 ECO_MCP_SERVERS 恒为空、连接器恒为 0 台。
    这里改用桩注入，验证的是「挂载后 inspect 能否看见」这段逻辑本身。
    """
    from agent_core import inspect as I
    from agent_core import tools_registry as tr

    fake = [
        {"type": "function", "function": {
            "name": "mcp__eia-emission__query_emission_gas_country",
            "description": "[MCP:eia-emission] 国家大气排放限值",
            "parameters": {"type": "object", "properties": {}}}},
        {"type": "function", "function": {
            "name": "mcp__eco-hunan-env__air_quality_hourly",
            "description": "[MCP:eco-hunan-env] 逐小时空气质量",
            "parameters": {"type": "object", "properties": {}}}},
    ]
    monkeypatch.setattr(tr, "ALL_TOOL_DEFS", list(tr.ALL_TOOL_DEFS) + fake)
    monkeypatch.setattr(tr, "attach_mcp_tools", lambda: [])  # 已由桩提供，不再真连

    names = {t["name"] for t in I.list_tools()}
    assert "mcp__eia-emission__query_emission_gas_country" in names, \
        "inspect 看不到已挂载的 MCP 工具 —— 自检存在盲区"
    assert "mcp__eco-hunan-env__air_quality_hourly" in names


def test_inspect_survives_attach_failure(monkeypatch):
    """attach 抛异常时 inspect 必须降级返回内置工具，不能整个炸掉。"""
    from agent_core import inspect as I
    from agent_core import tools_registry as tr

    def boom():
        raise RuntimeError("MCP 连接失败")

    monkeypatch.setattr(tr, "attach_mcp_tools", boom)
    tools = I.list_tools()
    assert isinstance(tools, list) and tools, "attach 失败不应让 inspect 返回空"


def test_rule_forbids_inferring_from_probe_failure():
    """硬规则 8.5：探测失败不能推断被探测对象的状态。"""
    src = (REPO / "server" / "api" / "chat.py").read_text(encoding="utf-8")
    assert "8.5" in src and "探测失败只能得出探测失败" in src
    for kw in ("Connection refused", "/api/v1/connectors", "正面证据"):
        assert kw in src, f"规则 8.5 缺少要素: {kw}"


def test_connectors_endpoint_triggers_attach():
    """/connectors 也必须先确保挂载，不能用「还没连」冒充「连不上」。

    实测冷启动后首次调用曾返回 14 台全部 connected=False、tool_total=0，
    而它们其实连得好好的（跑过一轮对话后再查就是 14/14、487 工具）。
    自检端点报错误状态，正是这次事故的同一类根因。
    """
    src = (REPO / "server" / "api" / "connectors.py").read_text(encoding="utf-8")
    assert "attach_mcp_tools()" in src, "/connectors 应触发挂载"


def test_all_selfcheck_paths_consistent():
    """三个自检出口不能各说各话：inspect / connectors / 对话通道。"""
    for f, need in (
        ("agent_core/inspect.py", "attach_mcp_tools()"),
        ("server/api/connectors.py", "attach_mcp_tools()"),
    ):
        src = (REPO / f).read_text(encoding="utf-8")
        assert need in src, f"{f} 缺少挂载保障，自检口径会分裂"


# ── MCP 挂载重试语义 ──────────────────────────────────────────
# 预热把挂载提前到启动瞬间，放大了原有缺陷：_MCP_ATTACHED 在尝试「之前」
# 就置 True，一次部分失败就永久锁死。实测启动时远程 9 台不可达，
# 只连上 5 台，之后整个进程再不重试，connectors 稳定报 5/14。

class _FakeMgr:
    """按预设序列返回 connect_all 结果的假 manager。"""

    def __init__(self, statuses):
        self.configs = [object()]
        self._s = list(statuses)
        self.calls = 0

    def connect_all(self):
        r = self._s[min(self.calls, len(self._s) - 1)]
        self.calls += 1
        return r

    def all_tools(self):
        return []

    def close(self):
        pass


def _reset(tr):
    tr._MCP_ATTACHED = False
    tr._MCP_MGR = None
    tr._MCP_LAST_TRY = None


def test_partial_failure_keeps_retry_open(monkeypatch):
    """部分连上时不能锁死 —— 远程抖一下不该让进程永久降级。"""
    import agent_core.mcp_connector as mc
    from agent_core import tools_registry as tr

    fake = _FakeMgr([{"a": True, "b": False}])
    monkeypatch.setattr(mc, "MCP_AVAILABLE", True)
    monkeypatch.setattr(mc, "MCPConnectorManager", lambda *a, **k: fake)
    _reset(tr)
    tr.attach_mcp_tools()
    assert tr._MCP_ATTACHED is False, "部分失败被当成挂载完成，会永久锁死"


def test_full_success_locks_in(monkeypatch):
    """全部连上才锁定，之后不再重连。"""
    import agent_core.mcp_connector as mc
    from agent_core import tools_registry as tr

    fake = _FakeMgr([{"a": True, "b": True}])
    monkeypatch.setattr(mc, "MCP_AVAILABLE", True)
    monkeypatch.setattr(mc, "MCPConnectorManager", lambda *a, **k: fake)
    _reset(tr)
    tr.attach_mcp_tools()
    assert tr._MCP_ATTACHED is True
    tr.attach_mcp_tools()
    assert fake.calls == 1, "已锁定后不应重连"


def test_retry_actually_reconnects(monkeypatch):
    """冷却窗口过后确实会重试，并在成功时补齐。"""
    import agent_core.mcp_connector as mc
    from agent_core import tools_registry as tr

    fake = _FakeMgr([{"a": True, "b": False}, {"a": True, "b": True}])
    monkeypatch.setattr(mc, "MCP_AVAILABLE", True)
    monkeypatch.setattr(mc, "MCPConnectorManager", lambda *a, **k: fake)
    _reset(tr)
    tr.attach_mcp_tools()
    tr._MCP_LAST_TRY = None  # 模拟冷却结束
    tr.attach_mcp_tools()
    assert fake.calls == 2, "冷却过后应重试"
    assert tr._MCP_ATTACHED is True, "补连成功后应锁定"


def test_cooldown_blocks_reconnect_storm(monkeypatch):
    """冷却期内不重连 —— 对不可达主机 connect_all 是 12 秒级超时，
    无冷却会让每个请求都去重连，把服务拖死。"""
    import agent_core.mcp_connector as mc
    from agent_core import tools_registry as tr

    fake = _FakeMgr([{"a": True, "b": False}])
    monkeypatch.setattr(mc, "MCP_AVAILABLE", True)
    monkeypatch.setattr(mc, "MCPConnectorManager", lambda *a, **k: fake)
    _reset(tr)
    for _ in range(5):
        tr.attach_mcp_tools()
    assert fake.calls == 1, f"冷却未生效，重连了 {fake.calls} 次"
    assert tr._MCP_RETRY_COOLDOWN >= 60, "冷却窗口过短，仍可能形成请求风暴"


def test_no_config_locks_in(monkeypatch):
    """没有配置是永久事实，不必反复重试。"""
    import agent_core.mcp_connector as mc
    from agent_core import tools_registry as tr

    class _Empty:
        configs = []

        def close(self):
            pass

    monkeypatch.setattr(mc, "MCP_AVAILABLE", True)
    monkeypatch.setattr(mc, "MCPConnectorManager", lambda *a, **k: _Empty())
    _reset(tr)
    tr.attach_mcp_tools()
    assert tr._MCP_ATTACHED is True, "无配置应直接锁定，避免无谓重试"


def test_startup_warms_mcp():
    """启动时后台预热，避免首个请求撞上 66.8 秒冷启动。"""
    src = (REPO / "server" / "app.py").read_text(encoding="utf-8")
    assert "_warm_mcp" in src and "attach_mcp_tools()" in src


def test_probe_classifies_failure_kinds():
    """失败必须分类，不能全塞进一句「请求失败」。

    模型无从区分「端口没服务」和「服务在冷启动」时，只能猜 ——
    实测就猜成了「没有单独运行的外部服务网关服务」，
    而真相是 14 台连接器全在跑，只是首次挂载要几十秒。
    """
    src = (REPO / "agent_core" / "exec_tools.py").read_text(encoding="utf-8")
    for kind in ('"timeout"', '"refused"'):
        assert kind in src, f"api_probe 未区分 {kind} 类失败"
    assert "探测失败只能证明这次访问没成功" in src, "失败返回值应自带解读约束"


def test_probe_refused_carries_hint():
    """端到端：连接被拒时返回 failure/hint/note 三件套。"""
    import asyncio
    import json as _json

    from server.api.chat import _run_tool

    r = _json.loads(asyncio.run(_run_tool("api_probe", {"url": "http://127.0.0.1:9/x"})))
    assert r.get("ok") is False
    assert r.get("failure") in ("refused", "timeout", "error")
    assert r.get("hint"), "失败应给出下一步动作指引"
    assert "不能据此断言" in str(r.get("note", "")), "缺少反过度推断约束"


def test_api_probe_runs_off_event_loop():
    """api_probe 必须在线程池执行，否则探自己的端点会自死锁。

    api_probe 用同步 urllib 请求「本进程自己的端点」。在事件循环里直接跑，
    循环被这次调用占住 → 本进程无法处理那个 HTTP 请求 → 15 秒后超时。
    实测自检探 /api/v1/connectors 必超时，而同一端点 curl 只要 3 毫秒；
    模型据此得出「无法获取远程 MCP 连通状态 [待确认]」。
    """
    src = (REPO / "server" / "api" / "chat.py").read_text(encoding="utf-8")
    i = src.index('if name in ("grep", "glob", "api_probe")')
    seg = src[i:i + 1600]
    assert "run_in_executor" in seg, "api_probe 仍在事件循环上同步执行，会自死锁"


def test_connectors_endpoint_off_event_loop():
    """/connectors 同样：_rows() 可能触发数十秒挂载，不能阻塞循环。"""
    src = (REPO / "server" / "api" / "connectors.py").read_text(encoding="utf-8")
    assert "run_in_executor" in src, "_rows() 阻塞事件循环"


# ── 规则 8.7 / 8.8：失败原因只能引用，工具名必须存在 ──────────────
# 真实事故：permit-remote 掉线，call_tool 只回一句 "server 未连接"，
# 模型编成「search_permit_list 处于 L3 非白名单，需运维加白名单后重试」。
# 三处都错：工具名不存在（真名 permit_pub_search_licenses）、
# 那台服务器本就在只读白名单里、算出来是 L1、全程无权限拒绝。

def test_rule_forbids_fabricating_failure_reason():
    src = (REPO / "server" / "api" / "chat.py").read_text(encoding="utf-8")
    assert "8.7" in src and "失败原因只能引用" in src
    for kw in ("ClosedResourceError", "permission denied [L3]", "远程服务当前不可用"):
        assert kw in src, f"规则 8.7 缺少要素: {kw}"


def test_rule_requires_tool_name_verification():
    src = (REPO / "server" / "api" / "chat.py").read_text(encoding="utf-8")
    assert "8.8" in src and "工具名必须先确认存在" in src
    assert "search_permit_list" in src, "应写明这次编造的具体工具名作为反例"


def test_permit_server_is_l1_not_l3():
    """坐实：permit-remote 的工具是 L1，不是模型说的 L3 非白名单。"""
    from agent_core.permissions import _READONLY_MCP_SERVERS, tool_risk_level

    assert "eco-pollution-permit-remote" in _READONLY_MCP_SERVERS
    for t in ("permit_pub_search_licenses", "permit_pub_license_detail",
              "permit_pub_discharge_points", "permit_pub_license_pages"):
        lv = tool_risk_level(f"mcp__eco-pollution-permit-remote__{t}")
        assert lv == "L1", f"{t} 实际为 {lv}，与「L3 需运维开放」的说法矛盾"


def test_call_tool_reconnects_before_giving_up():
    """掉线时先重连再放弃，否则一台掉线后本进程内就永久不可用。"""
    src = (REPO / "agent_core" / "mcp_connector.py").read_text(encoding="utf-8")
    i = src.index("def call_tool(")
    seg = src[i:i + 1800]
    assert "self.reconnect()" in seg, "call_tool 未在放弃前尝试重连"
    assert '"unreachable"' in seg, "应明确标注为连接类失败"


def test_call_tool_classifies_connection_errors():
    """ClosedResourceError 的 str() 是空的，必须显式分类，
    否则模型看到 'ClosedResourceError: ' 只能靠猜。"""
    src = (REPO / "agent_core" / "mcp_connector.py").read_text(encoding="utf-8")
    assert "ClosedResourceError" in src
    assert "与权限、白名单无关" in src, "错误提示应排除权限误判"


def test_health_check_is_concurrent():
    """必须并发 —— 串行重连 9 台不可达服务器实测跑满 5 分钟仍未返回。"""
    src = (REPO / "agent_core" / "mcp_connector.py").read_text(encoding="utf-8")
    i = src.index("def health_check(")
    seg = src[i:i + 2000]
    assert "asyncio.gather" in seg, "health_check 仍是串行，会超时"
    assert "timeout" in seg, "缺少总时限兜底"


def test_health_endpoint_and_loop_wired():
    """手动端点 + 后台巡检都要接上。"""
    conn = (REPO / "server" / "api" / "connectors.py").read_text(encoding="utf-8")
    assert "/connectors/health" in conn and "health_check" in conn
    app = (REPO / "server" / "app.py").read_text(encoding="utf-8")
    assert "_mcp_health_loop" in app, "缺少后台周期巡检"


def test_real_cli_entry_registers_port():
    """真正的启动入口是 eco/commands/cmd_server.py，
    server.app.run() 不经过那条路径 —— 端口登记必须加在这里。"""
    src = (REPO / "eco" / "commands" / "cmd_server.py").read_text(encoding="utf-8")
    assert "register_self_port(args.port)" in src
    assert 'os.environ["ECO_PORT"]' in src
