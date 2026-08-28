#!/usr/bin/env python3
"""
_scripts/setup_tencent_docs.py — 腾讯文档 MCP Token 本机自助配置

用法:
    python3 _scripts/setup_tencent_docs.py

流程:
    1. 交互式输入 Token（getpass：终端不回显、不进 shell 历史、不经聊天）
    2. 更新仓库 .env 中 ECO_MCP_SERVERS 的 tencent_docs 条目 Authorization 头
    3. 校验 JSON 完整性，输出结果（Token 脱敏显示）

Token 全程只落两个地方：你的输入动作 + 本机 .env 文件。不打印、不入日志、
不经任何网络传输（调用腾讯文档时由本机服务器直连，见 .env 注释）。

可选参数:
    --env-file PATH  指定 .env 路径（测试用；默认仓库 .env）
    --check          只检查当前配置状态（不要求输入）
    --clear          清除 tencent_docs 条目（登出）

安全说明:
    本脚本只改 .env 一行内容，不读不写其他文件；token 经 getpass 获取，
    不会出现在 ps/终端回显/shell 历史/任何日志里。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ENV = ROOT / ".env"

TDOCS_NAME = "tencent_docs"
TDOCS_URL = "https://docs.qq.com/openapi/mcp"


def _mask(token: str) -> str:
    if not token:
        return "(空)"
    if len(token) <= 8:
        return token[:2] + "***"
    return token[:4] + "…" + token[-4:]


def _load_servers(env_path: Path) -> tuple[list, str, int]:
    """读取 ECO_MCP_SERVERS 行，返回 (servers列表, 原始行, 行号)。找不到返回 ([], "", -1)。"""
    if not env_path.exists():
        return [], "", -1
    lines = env_path.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        if line.strip().startswith("ECO_MCP_SERVERS="):
            raw = line.split("=", 1)[1].strip()
            try:
                servers = json.loads(raw)
                return servers, line, i
            except json.JSONDecodeError as e:
                print(f"[错误] .env 里 ECO_MCP_SERVERS 不是合法 JSON: {e}")
                sys.exit(2)
    return [], "", -1


def _save_servers(env_path: Path, servers: list, old_line: str, line_no: int) -> bool:
    new_raw = json.dumps(servers, ensure_ascii=False, separators=(",", ":"))
    new_line = "ECO_MCP_SERVERS=" + new_raw
    lines = env_path.read_text(encoding="utf-8").splitlines()
    if line_no >= 0:
        lines[line_no] = new_line
    else:
        lines.append(new_line)
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


def find_tdocs(servers: list) -> dict | None:
    for s in servers:
        if isinstance(s, dict) and s.get("name") == TDOCS_NAME:
            return s
    return None


def set_token(env_path: Path, token: str) -> dict:
    servers, old_line, line_no = _load_servers(env_path)
    if not servers:
        print(f"[错误] {env_path} 中没有 ECO_MCP_SERVERS 配置")
        sys.exit(3)
    entry = find_tdocs(servers)
    if entry is None:
        # 追加官方条目（transport=http 由 mcp_connector 支持）
        entry = {"name": TDOCS_NAME, "transport": "http", "url": TDOCS_URL, "headers": {}}
        servers.append(entry)
    entry["transport"] = "http"
    entry["url"] = TDOCS_URL
    headers = entry.setdefault("headers", {})
    headers["Authorization"] = token
    _save_servers(env_path, servers, old_line, line_no)
    # 复读校验
    check_servers, _, _ = _load_servers(env_path)
    ok = (find_tdocs(check_servers) or {}).get("headers", {}).get("Authorization") == token
    return {"ok": ok, "masked": _mask(token)}


def clear_token(env_path: Path) -> dict:
    servers, old_line, line_no = _load_servers(env_path)
    if not servers:
        print(f"[错误] {env_path} 中没有 ECO_MCP_SERVERS 配置")
        sys.exit(3)
    entry = find_tdocs(servers)
    if entry is None:
        return {"ok": True, "removed": False}
    servers.remove(entry)
    _save_servers(env_path, servers, old_line, line_no)
    return {"ok": True, "removed": True}


def check(env_path: Path) -> dict:
    servers, _, _ = _load_servers(env_path)
    entry = find_tdocs(servers or [])
    if entry is None:
        return {"configured": False, "reason": "tencent_docs 条目不存在"}
    token = (entry.get("headers") or {}).get("Authorization", "")
    return {
        "configured": True,
        "transport": entry.get("transport"),
        "url": entry.get("url"),
        "token": _mask(token),
        "ready": bool(token) and "PASTE_TOKEN_HERE" not in token,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="腾讯文档 MCP Token 本机自助配置")
    ap.add_argument("--env-file", default=str(DEFAULT_ENV))
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--clear", action="store_true")
    args = ap.parse_args()
    env_path = Path(args.env_file)

    if args.check:
        print(json.dumps(check(env_path), ensure_ascii=False, indent=1))
        return
    if args.clear:
        print(json.dumps(clear_token(env_path), ensure_ascii=False, indent=1))
        return

    try:
        import getpass
        token = getpass.getpass("粘贴腾讯文档 Token（输入不回显，直接粘贴后回车）: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n已取消。")
        sys.exit(1)
    if not token:
        print("[错误] Token 为空，未修改配置。")
        sys.exit(1)
    if "PASTE_TOKEN_HERE" in token:
        print("[错误] 检测到占位符，请粘贴真实 Token。")
        sys.exit(1)
    result = set_token(env_path, token)
    if result["ok"]:
        print(f"[完成] Token 已写入 {env_path}（脱敏: {result['masked']}）")
        print("[下一步] 告诉开发者'已配置'，由他重启服务并接通聊天工具；或自行重启:")
        print("         cd /Users/mac/Documents/deepseek/eco-agent && python3 -m eco.cli server --port 8321")
    else:
        print("[错误] 写入后校验失败，请检查 .env 内容。")
        sys.exit(2)


if __name__ == "__main__":
    main()
