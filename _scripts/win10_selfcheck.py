#!/usr/bin/env python3
"""Windows 10 兼容性自检 — 穿透取证工具（grep/glob/api_probe/file_read）

用途
====
本机开发环境是 macOS，无法实测 Windows。本脚本把跨平台风险点做成可执行断言，
在 Win10 上跑一次即可拿到实测证据（而不是"应该能跑"的推断）。

用法（Windows PowerShell 或 CMD，在 eco-agent 目录下）：

    python _scripts\\win10_selfcheck.py

全部通过会打印 ALL PASS 并以 0 退出；任何一项失败以 1 退出并列出原因。
把完整输出回贴即可。
"""

from __future__ import annotations

import json
import os
import platform
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, bool(ok), detail))
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {name}" + (f" — {detail}" if detail else ""), flush=True)


def main() -> int:
    print("=" * 68)
    print("Windows 10 兼容性自检 — 穿透取证工具")
    print(f"Python  : {sys.version.split()[0]} ({platform.python_implementation()})")
    print(f"平台    : {platform.system()} {platform.release()}")
    print(f"仓库根  : {ROOT}")
    print("=" * 68)

    if sys.version_info < (3, 10):
        print(f"\n[警告] 项目要求 Python >= 3.10，当前 {sys.version_info.major}.{sys.version_info.minor}，"
              "部分模块会因 `X | None` 类型标注在导入期报 TypeError。")

    try:
        from agent_core.exec_tools import (
            _is_loopback_host,
            _resolve_within,
            api_probe,
            code_glob,
            code_grep,
            file_read,
            run_shell,
        )
    except Exception as e:  # noqa: BLE001
        print(f"\n[致命] 导入 agent_core.exec_tools 失败: {type(e).__name__}: {e}")
        return 1

    # ── 1. 环回判定：等价写法不得绕过或误拒 ──
    loop_cases = [("127.0.0.1", True), ("localhost", True), ("::1", True),
                  ("127.1", True), ("2130706433", True),
                  ("8.8.8.8", False), ("169.254.169.254", False), ("0.0.0.0", False)]
    bad = [h for h, exp in loop_cases if _is_loopback_host(h) is not exp]
    check("环回地址判定（含点分简写/整数形式）", not bad, f"异常项: {bad}" if bad else "8 项全对")

    # ── 2. glob：反斜杠模式（Windows 习惯写法）──
    r = json.loads(code_glob(r"agent_core\exec_tools.py"))
    check("glob 接受反斜杠模式", r.get("ok") and r.get("count", 0) >= 1,
          f"命中 {r.get('count')} 个")

    # ── 3. glob：正斜杠模式同样可用 ──
    r2 = json.loads(code_glob("agent_core/exec_tools.py"))
    check("glob 接受正斜杠模式", r2.get("ok") and r2.get("count", 0) >= 1,
          f"命中 {r2.get('count')} 个")

    # ── 4. grep：能定位到行 ──
    g = json.loads(code_grep(r"^def code_grep", include="*.py"))
    check("grep 正则定位到行", g.get("ok") and g.get("match_count", 0) >= 1,
          f"{g.get('match_count')} 处命中")

    # ── 5. grep：遍历遇到无权限目录不应整体失败 ──
    # 用不易命中上限的模式，确保真的走完了目录树而非提前触顶返回
    g2 = json.loads(code_grep(r"_is_loopback_host", include="*.py"))
    check("grep 全仓遍历不被单个不可访问项打断",
          g2.get("ok") is True and g2.get("scanned_files", 0) > 50,
          f"扫描 {g2.get('scanned_files')} 个文件，命中 {g2.get('match_count')} 处")

    # ── 6. 路径边界：兄弟前缀目录不得被当作子路径 ──
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        (tdp / "repo").mkdir()
        (tdp / "repo-evil").mkdir()
        victim = tdp / "repo-evil" / "x.txt"
        victim.write_text("secret", encoding="utf-8")
        import agent_core.exec_tools as et

        orig = et._allowed_roots
        et._allowed_roots = lambda: [tdp / "repo"]  # type: ignore[assignment]
        try:
            resolved, err = _resolve_within(str(victim), for_write=False)
            check("路径边界拒绝兄弟前缀目录（repo-evil vs repo）",
                  resolved is None, err or "已拒绝")
            inside = tdp / "repo" / "ok.txt"
            inside.write_text("hi", encoding="utf-8")
            resolved2, err2 = _resolve_within(str(inside), for_write=False)
            check("路径边界放行根内文件", resolved2 is not None, err2 or "已放行")
        finally:
            et._allowed_roots = orig  # type: ignore[assignment]

    # ── 7. CRLF 文件分页行号 ──
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        import agent_core.exec_tools as et

        orig = et._allowed_roots
        et._allowed_roots = lambda: [tdp]  # type: ignore[assignment]
        try:
            f = tdp / "crlf.txt"
            f.write_bytes(b"l1\r\nl2\r\nl3\r\nl4\r\n")
            rr = json.loads(file_read(str(f), offset=2, limit=2))
            ok = (rr.get("ok") and rr.get("start_line") == 2
                  and "2: l2" in rr.get("content", "") and "\r" not in rr.get("content", ""))
            check("CRLF 文件按行分页 + 行号正确", ok, f"start_line={rr.get('start_line')}")
        finally:
            et._allowed_roots = orig  # type: ignore[assignment]

    # ── 8. 绝对路径要求（Win 盘符形式）──
    rel = json.loads(file_read("relative_path.py"))
    check("拒绝相对路径", rel.get("ok") is False, rel.get("error", ""))

    # ── 9. shell 白名单：curl 仍封禁 ──
    sh = json.loads(run_shell("curl http://127.0.0.1/"))
    check("shell 仍封禁 curl（api_probe 是唯一窄通道）", sh.get("ok") is False)

    # ── 10. shell 基本命令在 Windows 上的可用性（信息项，不判失败）──
    pwd = json.loads(run_shell("pwd"))
    if not pwd.get("ok"):
        print(f"[INFO] shell_run('pwd') 在本平台不可用: {pwd.get('error', '')[:80]}")
        print("       Windows 无 pwd/ls 等 POSIX 命令，shell_run 的只读命令集在 Win 上受限；")
        print("       但 grep/glob/file_read/api_probe 不依赖 shell，取证能力不受影响。")
    else:
        print(f"[INFO] shell_run('pwd') 可用: {pwd.get('stdout', '').strip()[:60]}")

    # ── 11. api_probe 拒绝外网（不需要服务在跑）──
    p = json.loads(api_probe("http://8.8.8.8/x"))
    check("api_probe 拒绝非环回地址", p.get("ok") is False, p.get("error", "")[:50])
    p2 = json.loads(api_probe("/api/health", method="POST"))
    check("api_probe 拒绝写方法", p2.get("ok") is False, p2.get("error", "")[:50])

    # ── 12. api_probe 连本机服务（服务未启动时为信息项）──
    port = os.environ.get("ECO_PORT", "8000")
    p3 = json.loads(api_probe("/api/health"))
    if p3.get("ok"):
        print(f"[INFO] 本机服务可达 :{port} — HTTP {p3.get('status')}")
    else:
        print(f"[INFO] 本机服务未启动或 /api/health 不存在（端口 {port}）：{str(p3.get('error'))[:60]}")
        print("       这不算失败；启动服务后可再跑一次验证真实取证链路。")

    print("=" * 68)
    failed = [n for n, ok, _ in results if not ok]
    if failed:
        print(f"FAILED {len(failed)}/{len(results)}：")
        for n in failed:
            print(f"  - {n}")
        return 1
    print(f"ALL PASS ({len(results)}/{len(results)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
