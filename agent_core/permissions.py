#!/usr/bin/env python3
"""
permissions.py — L1-L4 风险权限模型 + 工具执行闸门（PERMISSION.md 真实化）

风险等级（与 profiles/eco-agent/PERMISSION.md 对齐）：
  L1 READ         只读查询               -> 自动放行
  L2 WRITE_LOCAL  本地安全区写入          -> 自动放行
  L3 EXEC         命令/代码执行           -> 白名单自动放行，否则需人工确认
  L4 EXTERNAL     外部服务写入/网络操作    -> 必须人工确认（非交互模式拒绝并记日志）

工具分级：
  1. 默认映射表（按工具名前缀，见 _PREFIX_RISK）
  2. PERMISSION.md 中 ```yaml tool_risk_overrides 代码块逐工具覆盖：
       tool_risk_overrides:
         - tool: execute_code
           level: L3
  3. 未知工具默认 L3（保守）

执行闸门 gate_tool_call()：
  - 每次判定写 prompt_engine SM3 审计链（source=permission）
  - 交互模式（stdin 是 tty 且未设 ECO_NONINTERACTIVE）：CLI y/n 确认
  - 非交互模式：L3 白名单放行，L3 非白名单拒绝；L4 无 grant 时登记审批栈
    pending 请求（policy=ask）或维持原拒绝（policy=never），见 agent_core.approval
"""

import logging
import os
import re
import sys
from pathlib import Path

logger = logging.getLogger("permissions")

LEVELS = ("L1", "L2", "L3", "L4")
LEVEL_LABELS = {"L1": "READ", "L2": "WRITE_LOCAL", "L3": "EXEC", "L4": "EXTERNAL"}

# 默认映射表：按工具名前缀分级（顺序即优先级，先匹配先生效）
_PREFIX_RISK: list[tuple[tuple[str, ...], str]] = [
    # L3 — 命令/代码执行
    (("execute_code", "execute_", "shell", "exec_"), "L3"),
    # L4 — 外部服务写操作（政务办理/审批/交易/设备控制/网络写）
    (("apply_", "book_", "submit_", "register_", "trade_", "set_",
      "configure_", "control_", "dispatch_", "handle_", "initiate_",
      "manage_", "input_", "generate_approval_document",
      "apply_approval_digital_signature"), "L4"),
    # L2 — 本地安全区写入
    (("workspace_", "memory_", "generate_", "write_", "save_"), "L2"),
    # L1 — 只读查询/检索/分析（宽前缀兜底）
    (("query_", "get_", "search_", "kb_", "calculate_", "predict_",
      "analyze_", "detect_", "vision_", "ocr_", "monitor_",
      "supervise_", "track_", "read_", "list_"), "L1"),
]

DEFAULT_UNKNOWN_LEVEL = "L3"  # 未知工具保守按 EXEC 处理

# L3 命令白名单（与 PERMISSION.md allow_auto 对齐；可在该文件增补）
L3_COMMAND_WHITELIST = [
    "python _scripts/lint.py",
    "python _scripts/quality_audit.py",
    "git ",
    "pip install ",
]

_REPO_PROFILES = Path(__file__).resolve().parent.parent / "profiles"


def _permission_md_paths() -> list[Path]:
    paths = []
    env = os.environ.get("ECO_PROFILES_DIR", "").strip()
    if env:
        paths.append(Path(env).expanduser() / "eco-agent" / "PERMISSION.md")
    paths.append(Path.home() / ".eco" / "profiles" / "eco-agent" / "PERMISSION.md")
    paths.append(_REPO_PROFILES / "eco-agent" / "PERMISSION.md")
    return paths


def _load_permission_md() -> str:
    for p in _permission_md_paths():
        if p.exists():
            try:
                return p.read_text(encoding="utf-8")
            except OSError:
                continue
    return ""


_OVERRIDE_RE = re.compile(
    r"tool_risk_overrides:\s*\n((?:\s*-\s*tool:.*\n(?:\s+level:.*\n)?)+)")


def load_overrides() -> dict[str, str]:
    """从 PERMISSION.md 的 tool_risk_overrides 块解析逐工具覆盖（无 PyYAML 依赖）。

    用块切片法（取 tool_risk_overrides: 到代码围栏 ``` 之间的全部文本），
    容忍条目间的注释行/空行——正则整体匹配曾被注释行截断，
    导致注释后新增的条目全部漏解析（如三平台 L1 批量条目）。"""
    text = _load_permission_md()
    overrides: dict[str, str] = {}
    i = text.find("tool_risk_overrides:")
    if i < 0:
        return overrides
    tail = text[i:]
    fence = tail.find("```", tail.find("\n") + 1)
    block = tail[:fence] if fence >= 0 else tail
    for tm in re.finditer(r"-\s*tool:\s*([A-Za-z0-9_-]+)\s*\n\s*level:\s*(L[1-4])", block):
        overrides[tm.group(1)] = tm.group(2)
    if overrides:
        logger.info(f"[permissions] PERMISSION.md 覆盖 {len(overrides)} 项工具风险级")
    return overrides


def load_l3_whitelist() -> list[str]:
    """L3 白名单：内置 + PERMISSION.md L3 allow_auto command 条目增补"""
    wl = list(L3_COMMAND_WHITELIST)
    text = _load_permission_md()
    # 仅解析 L3 段 allow_auto 子块（require_approval 中的命令绝不进入白名单）
    m = re.search(r"###\s*L3.*?allow_auto:(.*?)(?:require_approval:|deny:|```)", text, re.DOTALL)
    if m:
        for cm in re.finditer(r"-\s*command:\s*\"([^\"]+)\"", m.group(1)):
            cmd = cm.group(1).rstrip("*").strip()
            if cmd and cmd not in wl:
                wl.append(cmd + " " if not cmd.endswith(" ") else cmd)
    return wl


def tool_risk_level(tool_name: str, overrides: dict[str, str] | None = None) -> str:
    """判定工具风险等级：覆盖表 > 前缀映射 > 未知默认 L3。
    注意：mcp__{server}__{tool} 远程工具不按内层名猜测风险——服务端不受信，
    写操作可以伪装成 query_ 前缀命名；MCP 工具一律走默认 L3，
    确需放行的只读工具在 PERMISSION.md tool_risk_overrides 逐名豁免（决策写 SM3 审计链）。"""
    if overrides is None:
        overrides = load_overrides()
    if tool_name in overrides:
        return overrides[tool_name]
    for prefixes, level in _PREFIX_RISK:
        if any(tool_name.startswith(p) for p in prefixes):
            return level
    return DEFAULT_UNKNOWN_LEVEL


def risk_table() -> dict[str, str]:
    """全部已注册工具的风险分级表（eco doctor / config 展示用）"""
    from agent_core.tools_registry import get_tool_names
    overrides = load_overrides()
    return {name: tool_risk_level(name, overrides) for name in get_tool_names()}


def _audit_decision(tool_name: str, level: str, decision: str, reason: str):
    """全部闸门决策写 SM3 审计链（source=permission）"""
    try:
        from agent_core.prompt_engine import get_prompt_engine
        get_prompt_engine().audit.append(
            source="permission",
            content=f"{tool_name} [{level}/{LEVEL_LABELS[level]}] -> {decision}: {reason}",
            phase="permission", accepted=(decision == "allow"), reason=reason)
    except Exception as e:  # noqa: BLE001 — 审计失败不阻断业务
        logger.warning(f"[permissions] 审计写入失败: {e}")


def _is_interactive() -> bool:
    if os.environ.get("ECO_NONINTERACTIVE", "").strip().lower() in ("1", "true", "yes"):
        return False
    try:
        return sys.stdin.isatty()
    except Exception:  # noqa: BLE001
        return False


def _confirm(prompt: str) -> bool:
    """CLI 交互式人工确认 y/n"""
    try:
        ans = input(prompt).strip().lower()
        return ans in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        print()
        return False


def gate_tool_call(tool_name: str, args: dict | None = None,
                   overrides: dict[str, str] | None = None) -> tuple[bool, str, str]:
    """执行闸门。返回 (是否放行, 风险级, 原因)。全部决策写审计链。

    overrides: 调用方注入的风险覆盖（如插件 manifest 声明），优先级同 load_overrides。
    """
    level = tool_risk_level(tool_name, overrides)

    if level in ("L1", "L2"):
        _audit_decision(tool_name, level, "allow", "自动放行")
        return True, level, "自动放行"

    if level == "L3":
        # execute_code 携带 code 参数时经 agent_core.sandbox 三层隔离执行
        # （Docker → bwrap/rlimit → 本地受限+超时+环境变量清洗），沙箱即安全边界，
        # 自动放行并审计——对齐 DSH 沙箱代码执行语义。无 code 的调用（command 形态）
        # 仍走下方白名单/确认路径。
        if tool_name == "execute_code" and (args or {}).get("code"):
            _audit_decision(tool_name, level, "allow", "沙箱隔离自动放行（code 经 sandbox 执行）")
            return True, level, "沙箱隔离自动放行"
        cmd = str((args or {}).get("command", "") or (args or {}).get("code", ""))
        whitelist = load_l3_whitelist()
        if cmd and any(cmd.startswith(w.strip()) for w in whitelist if w.strip()):
            _audit_decision(tool_name, level, "allow", f"白名单放行: {cmd[:60]}")
            return True, level, "白名单放行"
        if _is_interactive():
            ok = _confirm(f"⚠️  [权限闸门 L3/EXEC] 工具 {tool_name} 请求执行命令/代码"
                          f"{('：' + cmd[:80]) if cmd else ''}，是否允许？[y/N] ")
            decision = "allow" if ok else "deny"
            reason = "人工确认放行" if ok else "人工拒绝"
            _audit_decision(tool_name, level, decision, reason)
            return ok, level, reason
        _audit_decision(tool_name, level, "deny", "非交互模式拒绝（白名单外 L3）")
        return False, level, "非交互模式拒绝（白名单外 L3）"

    # L4 — 必须人工确认；先查有效授权令牌（非交互 L4 授权通道）
    try:
        from agent_core.grants import audit_grant_use, find_valid_grant
        g, _reason = find_valid_grant("L4", tool_name)
        if g is not None:
            _audit_decision(tool_name, level, "allow",
                            f"授权令牌放行 grant:{g.get('id')} (scope={g.get('scope')})")
            audit_grant_use(g, tool_name, level)
            return True, level, f"授权令牌放行 grant:{g.get('id')}"
    except Exception as e:  # noqa: BLE001 — 授权查询失败不越权，回落人工确认
        logger.warning(f"[permissions] 授权查询失败: {e}")

    if _is_interactive():
        kv = "; ".join(f"{k}={str(v)[:40]}" for k, v in list((args or {}).items())[:4])
        ok = _confirm(f"🛑 [权限闸门 L4/EXTERNAL] 工具 {tool_name}({kv}) 将调用外部服务/执行写操作，"
                      f"必须人工审批。是否允许？[y/N] ")
        decision = "allow" if ok else "deny"
        reason = "人工审批放行" if ok else "人工审批拒绝"
        _audit_decision(tool_name, level, decision, reason)
        return ok, level, reason
    # 非交互 L4 无 grant：交给审批栈（ask 登记 pending / never 维持原 deny 语义）
    try:
        from agent_core.approval import get_approval_service
        svc = get_approval_service()
        if svc.policy == "never":
            _audit_decision(tool_name, level, "deny", "非交互模式拒绝（L4 必须人工确认）")
            return False, level, "非交互模式拒绝（L4 必须人工确认）"
        req = svc.request(scope=tool_name, detail=args or {})
        reason = f"已提交审批请求 pending:{req.get('id')}，等待 answerer 决定"
        _audit_decision(tool_name, level, "pending", reason)
        return False, level, reason
    except Exception as e:  # noqa: BLE001 — 审批栈异常绝不越权放行，回落原 deny
        logger.warning(f"[permissions] 审批栈登记失败，回落 deny: {e}")
        _audit_decision(tool_name, level, "deny", "非交互模式拒绝（L4 必须人工确认）")
        return False, level, "非交互模式拒绝（L4 必须人工确认）"
