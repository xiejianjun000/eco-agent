#!/usr/bin/env python3
"""验收自检 — 不花 token，直接核对本轮三项改动是否真的落地

覆盖：
  A. 三层穿透能力（inspect / grep / glob / api_probe + 结论 gate）
  B. govmcp 方案 B 删除（政务工具清除、SM3 审计链保留、在用 MCP 未误删）
  C. 跨平台配置（.gitattributes 规则、换行归一化）

用法（Python 需 >= 3.10）：
    python _scripts/acceptance_check.py

全过打印 ALL PASS 并以 0 退出；失败列出具体项并以 1 退出。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

rows: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    rows.append((name, bool(ok), detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""), flush=True)


def section(t: str) -> None:
    print(f"\n── {t} " + "─" * max(0, 56 - len(t)))


def main() -> int:
    print("=" * 66)
    print("eco Agent 验收自检")
    print(f"Python {sys.version.split()[0]} | 仓库 {ROOT}")
    print("=" * 66)

    if sys.version_info < (3, 10):
        print("\n[致命] 本仓库要求 Python >= 3.10，当前版本会在导入期报 TypeError。")
        print("       请用 3.11/3.12 重跑本脚本。")
        return 1

    # ══ A. 三层穿透能力 ══
    section("A. 三层穿透能力")

    from agent_core.inspect import list_tools
    from server.api.chat import _codex_tools

    names = {t["function"]["name"] for t in _codex_tools()}
    want = ["inspect", "grep", "glob", "api_probe"]
    missing = [n for n in want if n not in names]
    check("L1 感知：4 个穿透工具已进聊天工具表", not missing,
          f"共 {len(names)} 个工具" if not missing else f"缺 {missing}")

    # 接线登记（CI 曾因此红）
    from agent_core.tools_registry import _HANDLERS, resolve_tool_name
    from agent_core.wiring_manifest import CHANNEL_DISPATCHED

    no_handler = [n for n in names
                  if n not in CHANNEL_DISPATCHED and n not in _HANDLERS
                  and resolve_tool_name(n) not in _HANDLERS]
    check("接线完整：聊天表内每个工具都有 handler", not no_handler,
          "无缺口" if not no_handler else f"缺 handler: {no_handler}")

    # inspect 能自省
    check("inspect 可自省工具全集", len(list_tools()) > 0, f"{len(list_tools())} 个")

    # L2 穿透：grep/glob 实际可用
    from agent_core.exec_tools import api_probe, code_glob, code_grep

    g = json.loads(code_grep(r"_sys_claim_trigger", include="*.py"))
    check("L2 穿透：grep 能定位源码", g.get("ok") and g.get("match_count", 0) > 0,
          f"{g.get('match_count')} 处命中")
    gl = json.loads(code_glob("exec_tools.py"))
    check("L2 穿透：glob 能发现文件", gl.get("ok") and gl.get("count", 0) > 0,
          f"{gl.get('count')} 个命中")

    # L3 验证：结论 gate 判别力（既要拦系统结论，又不能误伤执法业务结论）
    from server.api.chat import _sys_claim_trigger as trig

    fire = ["当前有 5 个 MCP 没有挂载", "系统里工具注册数为 0",
            "govmcp 插件已挂载，运行正常", "api_probe 工具不存在"]
    nofire = ["该企业污水处理设施未正常运行", "排污许可证已过期",
              "现场检查未发现异常", "这家厂的在线监控设备没有联网",
              "该单位危废台账未如实记录"]
    bad_f = [s for s in fire if not trig(s)]
    bad_n = [s for s in nofire if trig(s)]
    check("L3 验证：系统状态结论会被 gate 拦截", not bad_f,
          f"{len(fire)}/{len(fire)} 触发" if not bad_f else f"漏拦: {bad_f}")
    check("L3 验证：执法业务结论不被误伤（关键）", not bad_n,
          f"{len(nofire)}/{len(nofire)} 放行" if not bad_n else f"误伤: {bad_n}")

    # api_probe 安全边界
    p1 = json.loads(api_probe("http://8.8.8.8/x"))
    p2 = json.loads(api_probe("/api/health", method="POST"))
    check("api_probe 仅限本机环回 + 只读方法",
          p1.get("ok") is False and p2.get("ok") is False)

    from agent_core.exec_tools import run_shell

    check("curl 仍封禁（api_probe 是唯一窄通道）",
          json.loads(run_shell("curl http://127.0.0.1/")).get("ok") is False)

    # ══ B. govmcp 方案 B ══
    section("B. govmcp 删除（方案 B）")

    leftover = [n for n in names
                if str(n).startswith(("wryzxjc_", "sthjzf_", "permit_"))
                or n in ("hunan_env_monthly_report", "water_station_realtime", "air_forecast")]
    check("31 个不可达政务工具已清除", not leftover,
          f"工具集 {len(names)} 个，无残留" if not leftover else f"残留 {leftover}")

    # SM3 审计链必须还在（选 B 的核心理由）
    import tempfile

    from agent_core.trace_audit import TraceAudit

    with tempfile.TemporaryDirectory() as d:
        a = TraceAudit(base_dir=d)
        for i in range(5):
            a.record_trace(user_msg=f"m{i}", reply="r", trace_len=1, duration_ms=1, model="t")
        v = a.verify()
    check("SM3 审计链完好（等保台账地基）", v.get("ok") is True, f"链校验 {v}")

    # 在用的两个外部 MCP 服务器源码必须还在（我曾误删后还原）
    for d_ in ("hunan-env-mcp", "mee-encyclopedia-mcp"):
        check(f"在用 MCP 服务器保留：{d_}", (ROOT / "govmcp" / d_).is_dir())

    # 协议层/工具包确实删干净
    for gone in ("govmcp/protocol", "govmcp/server", "govmcp_tools"):
        check(f"已删除：{gone}", not (ROOT / gone).exists())

    # ══ C. 跨平台配置 ══
    section("C. 跨平台配置")

    check(".gitattributes 已存在", (ROOT / ".gitattributes").is_file())

    def attr(path: str, a: str) -> str:
        r = subprocess.run(["git", "check-attr", a, "--", path],
                           capture_output=True, text=True, cwd=ROOT)
        return r.stdout.strip().rsplit(": ", 1)[-1] if r.returncode == 0 else "?"

    check("Python/Shell 强制 LF（防 Linux bad interpreter）",
          attr("agent_core/exec_tools.py", "eol") == "lf" and attr("x.sh", "eol") == "lf")
    check("Windows 脚本保持 CRLF", attr("x.bat", "eol") == "crlf")
    check("二进制禁止换行转换", attr("x.png", "binary") == "set")

    # 仓库内不应再有 CRLF 文本文件
    r = subprocess.run(["git", "ls-files", "-z"], capture_output=True, cwd=ROOT)
    crlf = []
    for f in r.stdout.split(b"\0"):
        if not f:
            continue
        fp = ROOT / f.decode("utf-8", "replace")
        if fp.suffix.lower() in (".py", ".sh", ".yml", ".yaml", ".md", ".json", ".toml"):
            try:
                if b"\r\n" in fp.read_bytes():
                    crlf.append(fp.name)
            except OSError:
                pass
    check("被跟踪文本文件无 CRLF 残留", not crlf,
          "全部 LF" if not crlf else f"{len(crlf)} 个仍是 CRLF: {crlf[:5]}")

    print("=" * 66)
    failed = [n for n, ok, _ in rows if not ok]
    if failed:
        print(f"FAILED {len(failed)}/{len(rows)}")
        for n in failed:
            print(f"  - {n}")
        return 1
    print(f"ALL PASS ({len(rows)}/{len(rows)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
