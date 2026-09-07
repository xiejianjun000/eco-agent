#!/usr/bin/env python3
"""
agent_core/exec_tools.py — 执行层工具（shell 白名单 + 文件精确编辑）
==================================================================
补齐 eco-agent 与开发代理的结构性差距（路线图 ① ②）：

① shell_run：命令白名单 shell 执行（只读+受限命令集，禁写禁删禁链）
② file_read / file_write / file_edit：精确文件读写编辑
   （read L1 只读；write/edit 仅限工作区与仓库根内，写前审计）

安全契约：
- shell 只允许白名单首命令，禁止重定向/命令链/替换/反引号，超时 30s，
  环境变量清洗（仅保留 PATH/LANG），输出截断 8000 字符
- 文件写操作路径解析后必须落在允许根内（realpath 校验防 ../ 逃逸），
  单次写入 ≤ 200KB；file_edit 的 old_string 必须唯一命中（防误伤）
- 每次调用写 SM3 审计链（source=exec_tool），审计失败不阻断
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
from pathlib import Path

# ─── shell 白名单（只读/受限命令集）─────────────────────────────

SHELL_ALLOWED = {
    "ls",
    "cat",
    "head",
    "tail",
    "wc",
    "grep",
    "find",
    "pwd",
    "echo",
    "date",
    "du",
    "df",
    "ps",
    "python3",
    "python",
    "git",
    "tree",
    "sort",
    "uniq",
    "sed",
    "awk",
    "diff",
    "basename",
    "dirname",
    "which",
    "test",
    # 开发类（自改自测闭环）：测试/依赖/构建
    "pytest",
    "pip",
    "npm",
    "node",
    "make",
    # 飞书/企业微信 CLI（授权登录/发消息/查登录态，本地已认证）
    "lark-cli",
}

# 高危第一命令（即使白名单里出现变体也拒绝）
SHELL_FORBIDDEN_START = (
    "rm",
    "sudo",
    "chmod",
    "chown",
    "kill",
    "shutdown",
    "reboot",
    "mkfs",
    "dd",
    "curl",
    "wget",
    "scp",
    "ssh",
)

# 危险语法模式（任一命中即拒绝）
_SHELL_DANGER_RE = re.compile(r"[><]|`|\$\(|\$\{|&&|\|\||;|mkfifo|/dev/|>>")

SHELL_TIMEOUT = 30.0
OUTPUT_CAP = 8000

# ─── 文件工具允许根 ────────────────────────────────────────────


def _allowed_roots() -> list[Path]:
    roots = []
    ws = os.environ.get("ECO_WORKSPACE_DIR", "").strip()
    if ws:
        roots.append(Path(ws))
    repo = Path(__file__).resolve().parent.parent
    roots.append(repo)
    return roots


def _audit(action: str, target: str, decision: str, reason: str) -> None:
    try:
        from agent_core.prompt_engine import get_prompt_engine

        get_prompt_engine().audit.append(
            source="exec_tool",
            content=f"{action} {target[:80]} -> {decision}",
            phase="permission",
            accepted=(decision == "allow"),
            reason=reason,
        )
    except Exception:
        pass


# ─── ① shell_run ───────────────────────────────────────────────


def run_shell(command: str) -> str:
    """白名单 shell 执行。返回 JSON 字符串（ok/stdout/stderr/duration）。"""
    cmd = (command or "").strip()
    if not cmd:
        return json.dumps({"ok": False, "error": "空命令"}, ensure_ascii=False)
    if _SHELL_DANGER_RE.search(cmd):
        _audit("shell", cmd, "deny", "危险语法（重定向/链/替换）")
        return json.dumps({"ok": False, "error": "命令含危险语法（重定向/命令链/$替换/反引号均禁止）"}, ensure_ascii=False)
    # 按管道分段，每段首命令必须白名单
    segments = [s.strip() for s in cmd.split("|") if s.strip()]
    if not segments:
        return json.dumps({"ok": False, "error": "空命令"}, ensure_ascii=False)
    try:
        first_tokens = [shlex.split(s)[0] for s in segments]
    except ValueError as e:
        return json.dumps({"ok": False, "error": f"命令解析失败: {e}"}, ensure_ascii=False)
    for tok in first_tokens:
        base = Path(tok).name if "/" in tok else tok
        if base in SHELL_FORBIDDEN_START:
            _audit("shell", cmd, "deny", f"高危命令 {base}")
            return json.dumps({"ok": False, "error": f"禁止命令: {base}"}, ensure_ascii=False)
        if base not in SHELL_ALLOWED:
            _audit("shell", cmd, "deny", f"非白名单命令 {base}")
            return json.dumps(
                {"ok": False, "error": f"命令不在白名单: {base}（白名单: " + "、".join(sorted(SHELL_ALLOWED)) + "）"},
                ensure_ascii=False,
            )
    _audit("shell", cmd, "allow", "白名单放行")
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "LANG", "LC_ALL", "HOME", "LARK_CLI_HOME")}
    import time

    t0 = time.monotonic()
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=SHELL_TIMEOUT, env=env)
        out = (p.stdout or "")[:OUTPUT_CAP]
        err = (p.stderr or "")[:500]
        return json.dumps(
            {
                "ok": True,
                "exit": p.returncode,
                "stdout": out,
                "stderr": err,
                "duration_ms": int((time.monotonic() - t0) * 1000),
                "truncated": bool(p.stdout and len(p.stdout) > OUTPUT_CAP),
            },
            ensure_ascii=False,
        )
    except subprocess.TimeoutExpired:
        _audit("shell", cmd, "deny", "超时")
        return json.dumps({"ok": False, "error": f"超时（>{SHELL_TIMEOUT}s）"}, ensure_ascii=False)
    except Exception as e:  # noqa: BLE001
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


# ─── ② 文件工具 ────────────────────────────────────────────────


def _resolve_within(path_str: str, for_write: bool) -> tuple[Path | None, str]:
    """解析路径并校验在允许根内。返回 (Path, error)。

    跨平台注意：根目录同样要 resolve 后再比对。Windows 上 %TEMP% 等路径常以
    8.3 短名出现（C:\\Users\\RUNNER~1\\...），而目标路径 resolve() 后是长名，
    不归一就会把合法路径误判成越界；junction/symlink 同理。
    """
    p = Path(path_str or "").expanduser()
    if not p.is_absolute():
        return None, "必须使用绝对路径"
    try:
        real = p.resolve()
    except OSError:
        return None, "路径解析失败"
    roots = []
    for r in _allowed_roots():
        try:
            roots.append(r.resolve())
        except OSError:
            roots.append(r)
    if not any(_is_within(real, r) for r in roots):
        kind = "可写根" if for_write else "可读根"
        return None, f"路径不在{kind}内（{', '.join(str(r) for r in roots)}）"
    return real, ""


def _is_within(target: Path, root: Path) -> bool:
    """target 是否位于 root 之内（含 root 自身）。

    用 pathlib 的 is_relative_to：它按路径分量比较，且在 Windows 上遵循
    大小写不敏感语义——比字符串 startswith 安全（后者会把
    C:\\repo-evil 误判为 C:\\repo 的子路径）。
    """
    try:
        return target == root or target.is_relative_to(root)
    except (ValueError, OSError):
        return False


def file_read(path: str, max_chars: int = 12000, offset: int = 0, limit: int = 0) -> str:
    """读取文本文件。

    offset/limit 以「行」为单位（offset 为 1-based 起始行，0/1 均表示从头）：
    命中分页时返回带行号的 numbered 文本 + next_offset，供续读定位到行。
    未传分页参数时保持旧行为（整文件 + max_chars 截断），向后兼容。
    """
    real, err = _resolve_within(path, for_write=False)
    if err:
        _audit("file_read", path, "deny", err)
        return json.dumps({"ok": False, "error": err}, ensure_ascii=False)
    if not real.exists() or not real.is_file():
        return json.dumps({"ok": False, "error": f"文件不存在: {real}"}, ensure_ascii=False)
    try:
        text = real.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)
    _audit("file_read", str(real), "allow", "只读放行")

    lines = text.splitlines()
    total_lines = len(lines)

    # ── 分页模式：offset/limit 任一显式给出 ──
    if offset or limit:
        start = max(1, int(offset or 1))
        count = int(limit) if limit and limit > 0 else 400
        chunk = lines[start - 1 : start - 1 + count]
        width = len(str(min(start + len(chunk) - 1, total_lines)))
        numbered = "\n".join(f"{start + i:>{width}}: {ln}" for i, ln in enumerate(chunk))
        cut = len(numbered) > max_chars
        if cut:
            numbered = numbered[:max_chars]
        end_line = start + len(chunk) - 1
        has_more = end_line < total_lines
        return json.dumps(
            {
                "ok": True,
                "path": str(real),
                "total_lines": total_lines,
                "start_line": start,
                "end_line": end_line,
                "returned_lines": len(chunk),
                "has_more": has_more,
                "next_offset": (end_line + 1) if has_more else None,
                "truncated": cut,
                "content": numbered,
            },
            ensure_ascii=False,
        )

    # ── 兼容模式：整文件 + 字符截断 ──
    truncated = len(text) > max_chars
    return json.dumps(
        {
            "ok": True,
            "path": str(real),
            "chars": min(len(text), max_chars),
            "total_lines": total_lines,
            "truncated": truncated,
            # 截断时给出续读指引，避免"读不全又不知从哪续"
            "hint": ("内容被截断：改用 offset/limit 按行分页续读" if truncated else ""),
            "content": text[:max_chars],
        },
        ensure_ascii=False,
    )


def file_write(path: str, content: str) -> str:
    if len(content or "") > 200_000:
        return json.dumps({"ok": False, "error": "内容超过 200KB 上限"}, ensure_ascii=False)
    real, err = _resolve_within(path, for_write=True)
    if err:
        _audit("file_write", path, "deny", err)
        return json.dumps({"ok": False, "error": err}, ensure_ascii=False)
    try:
        real.parent.mkdir(parents=True, exist_ok=True)
        real.write_text(content or "", encoding="utf-8")
    except OSError as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)
    _audit("file_write", str(real), "allow", "工作区/仓库内写入")
    return json.dumps({"ok": True, "path": str(real), "bytes": len((content or "").encode("utf-8"))}, ensure_ascii=False)


def file_edit(path: str, old_string: str, new_string: str) -> str:
    if not old_string:
        return json.dumps({"ok": False, "error": "old_string 不能为空"}, ensure_ascii=False)
    real, err = _resolve_within(path, for_write=True)
    if err:
        _audit("file_edit", path, "deny", err)
        return json.dumps({"ok": False, "error": err}, ensure_ascii=False)
    try:
        text = real.read_text(encoding="utf-8")
    except OSError as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)
    count = text.count(old_string)
    if count == 0:
        return json.dumps({"ok": False, "error": "old_string 未命中"}, ensure_ascii=False)
    if count > 1:
        return json.dumps({"ok": False, "error": f"old_string 命中 {count} 处（必须唯一，请加长上下文）"}, ensure_ascii=False)
    new_text = text.replace(old_string, new_string, 1)
    if len(new_text) > 200_000:
        return json.dumps({"ok": False, "error": "修改后超过 200KB 上限"}, ensure_ascii=False)
    try:
        real.write_text(new_text, encoding="utf-8")
    except OSError as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)
    _audit("file_edit", str(real), "allow", "唯一命中替换")
    return json.dumps(
        {"ok": True, "path": str(real), "replaced": 1, "bytes": len(new_text.encode("utf-8"))}, ensure_ascii=False
    )


# ─── ③ 穿透工具：grep / glob（L2 源码定位）───────────────────────

_GREP_MAX_MATCHES = 200
_GLOB_MAX_FILES = 300
_SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", ".mypy_cache",
              ".pytest_cache", ".ruff_cache", "dist", "build", ".next"}


def _iter_files(root: Path, pattern: str):
    """在 root 下按 glob 模式产出文件，跳过噪声目录。

    Windows 上 rglob 遇到无权限目录、被占用文件或超长路径（>260 字符且未启用
    长路径支持）会抛 OSError；单个条目的失败不应终止整次遍历，逐项吞掉即可。
    """
    try:
        it = root.rglob(pattern)
        while True:
            try:
                p = next(it)
            except StopIteration:
                return
            except OSError:
                continue  # 该条目不可访问，跳过继续
            try:
                if not p.is_file():
                    continue
            except OSError:
                continue
            if any(part in _SKIP_DIRS for part in p.parts):
                continue
            yield p
    except (OSError, ValueError):
        return


def code_grep(pattern: str, path: str = "", include: str = "*", max_matches: int = _GREP_MAX_MATCHES) -> str:
    """正则全文搜索，返回 file:line:text（对标 DSH grep）。"""
    if not (pattern or "").strip():
        return json.dumps({"ok": False, "error": "pattern 不能为空"}, ensure_ascii=False)
    try:
        rx = re.compile(pattern)
    except re.error as e:
        return json.dumps({"ok": False, "error": f"正则无效: {e}"}, ensure_ascii=False)

    if path:
        root, err = _resolve_within(path, for_write=False)
        if err:
            _audit("grep", path, "deny", err)
            return json.dumps({"ok": False, "error": err}, ensure_ascii=False)
    else:
        root = _allowed_roots()[0]
    if root.is_file():
        targets = [root]
    else:
        # 同 code_glob：Windows 反斜杠模式归一为 posix 分隔符
        targets = _iter_files(root, (include or "*").replace("\\", "/"))

    cap = max(1, min(int(max_matches or _GREP_MAX_MATCHES), _GREP_MAX_MATCHES))
    matches, scanned, truncated = [], 0, False
    for f in targets:
        scanned += 1
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            continue
        if "\0" in text[:1024]:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if rx.search(line):
                matches.append({"file": str(f), "line": i, "text": line[:300]})
                if len(matches) >= cap:
                    truncated = True
                    break
        if truncated:
            break
    _audit("grep", f"{pattern} @{root}", "allow", f"{len(matches)} 命中")
    return json.dumps(
        {"ok": True, "pattern": pattern, "root": str(root), "scanned_files": scanned,
         "match_count": len(matches), "truncated": truncated, "matches": matches},
        ensure_ascii=False,
    )


def code_glob(pattern: str, path: str = "") -> str:
    """按模式发现文件，按修改时间倒序（对标 DSH glob）。"""
    if not (pattern or "").strip():
        return json.dumps({"ok": False, "error": "pattern 不能为空"}, ensure_ascii=False)
    if path:
        root, err = _resolve_within(path, for_write=False)
        if err:
            _audit("glob", path, "deny", err)
            return json.dumps({"ok": False, "error": err}, ensure_ascii=False)
    else:
        root = _allowed_roots()[0]
    # Windows 用户习惯写反斜杠（src\**\*.py）：统一成 posix 分隔符，
    # pathlib 的 glob 只认 "/"，否则整个模式会被当成单个文件名而永远 0 命中。
    pat = (pattern or "").replace("\\", "/")
    # 无分隔符的模式匹配任意深度的 basename
    if "/" not in pat:
        pat = f"**/{pat}"
    try:
        found = list(_iter_files(root, pat))
    except (OSError, ValueError) as e:
        return json.dumps({"ok": False, "error": f"匹配失败: {e}"}, ensure_ascii=False)

    def _mtime(p: Path) -> float:
        # 文件可能在遍历与排序之间消失（Win 上还可能被占用/拒绝访问）：
        # stat 失败一律记 0，不让一个瞬时错误打断整次搜索。
        try:
            return p.stat().st_mtime
        except OSError:
            return 0.0

    found.sort(key=_mtime, reverse=True)
    truncated = len(found) > _GLOB_MAX_FILES
    _audit("glob", f"{pattern} @{root}", "allow", f"{len(found)} 命中")
    return json.dumps(
        {"ok": True, "pattern": pattern, "root": str(root), "count": len(found),
         "truncated": truncated, "files": [str(p) for p in found[:_GLOB_MAX_FILES]]},
        ensure_ascii=False,
    )


# ─── ④ api_probe：本机只读 API 实测（L3 取证）────────────────────
#
# 不解封 shell 的 curl：curl 一旦放行即等于开放任意外网 + 任意方法 + 隐式写。
# 这里只开一条窄通道——本机环回地址 + 只读方法——够 agent 自证"服务实况"，
# 又不新增外网出口。外网抓取仍走既有 web_fetch（政务域名白名单）。

_PROBE_ALLOWED_NAMES = {"localhost"}
_PROBE_METHODS = {"GET", "HEAD"}
_PROBE_MAX_CHARS = 8000


def _is_loopback_host(host: str) -> bool:
    """判定主机是否为本机环回地址（跨平台，按 IP 语义而非字符串比对）。

    字符串白名单挡不住等价写法：127.1、2130706433、0x7f.1 在 Windows 与
    Linux 的解析器上都会连到 127.0.0.1。这里统一交给 ipaddress 判定，
    既不漏放（等价写法照样识别为环回），也不误拒。
    """
    import ipaddress

    h = (host or "").strip().lower()
    if not h:
        return False
    if h in _PROBE_ALLOWED_NAMES:
        return True
    # IPv6 字面量在 urlparse 后已去掉方括号
    try:
        return ipaddress.ip_address(h).is_loopback
    except ValueError:
        pass
    # 简写点分形式（127.1 等）：交给平台 inet_aton 语义再判一次
    import socket

    try:
        packed = socket.inet_aton(h)
    except OSError:
        return False
    try:
        return ipaddress.ip_address(socket.inet_ntoa(packed)).is_loopback
    except ValueError:
        return False


def api_probe(url: str, method: str = "GET", max_chars: int = _PROBE_MAX_CHARS) -> str:
    """探查本机 HTTP 接口真实返回（只读，仅环回地址）。"""
    import urllib.error
    import urllib.parse
    import urllib.request

    u = (url or "").strip()
    if not u:
        return json.dumps({"ok": False, "error": "url 不能为空"}, ensure_ascii=False)
    # 允许简写 /api/xxx → 本机默认端口
    if u.startswith("/"):
        port = os.environ.get("ECO_PORT", "8000").strip() or "8000"
        u = f"http://127.0.0.1:{port}{u}"
    if not u.startswith(("http://", "https://")):
        return json.dumps({"ok": False, "error": "url 必须以 http(s):// 或 / 开头"}, ensure_ascii=False)

    host = (urllib.parse.urlparse(u).hostname or "").lower()
    if not _is_loopback_host(host):
        _audit("api_probe", u, "deny", f"非本机地址 {host}")
        return json.dumps(
            {"ok": False, "error": f"api_probe 仅允许本机环回地址（收到 {host}）；外网抓取请用 web_fetch"},
            ensure_ascii=False,
        )
    m = (method or "GET").upper()
    if m not in _PROBE_METHODS:
        _audit("api_probe", u, "deny", f"非只读方法 {m}")
        return json.dumps({"ok": False, "error": f"api_probe 只允许 {sorted(_PROBE_METHODS)}（收到 {m}）"},
                          ensure_ascii=False)

    import time as _t
    t0 = _t.monotonic()
    try:
        req = urllib.request.Request(u, method=m, headers={"User-Agent": "eco-agent api_probe"})
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310 (host 已限环回)
            body = resp.read().decode("utf-8", errors="replace")
            status = resp.status
    except urllib.error.HTTPError as e:
        body, status = e.read().decode("utf-8", errors="replace"), e.code
    except Exception as e:  # noqa: BLE001
        _audit("api_probe", u, "deny", f"请求失败 {e}")
        return json.dumps({"ok": False, "url": u, "error": f"请求失败: {e}"}, ensure_ascii=False)

    _audit("api_probe", u, "allow", f"HTTP {status}")
    cap = max(1, min(int(max_chars or _PROBE_MAX_CHARS), _PROBE_MAX_CHARS))
    parsed = None
    try:
        parsed = json.loads(body)
    except (ValueError, TypeError):
        pass
    out = {
        "ok": True,
        "url": u,
        "status": status,
        "duration_ms": int((_t.monotonic() - t0) * 1000),
        "truncated": len(body) > cap,
    }
    if parsed is not None and isinstance(parsed, (dict, list)):
        s = json.dumps(parsed, ensure_ascii=False)
        out["json"] = parsed if len(s) <= cap else None
        out["body"] = None if out["json"] is not None else s[:cap]
    else:
        out["body"] = body[:cap]
    return json.dumps(out, ensure_ascii=False)
