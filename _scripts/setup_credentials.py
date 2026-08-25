#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
_scripts/setup_credentials.py — eco-agent 凭证本机自助配置（一站式）

把所有"能力挂了但凭证没挂"的缺口收口到一个交互式入口：
  1. 娄底污染源在线监测     WRYZXJC_USERNAME / WRYZXJC_PASSWORD
  2. 国家四平台             STHJZF_USERNAME / STHJZF_PASSWORD
  3. 排污许可管理平台(内网)  PERMIT_BASE / PERMIT_JGZF_BASE / PERMIT_JGZF_KEY
                            / PERMIT_USERNAME / PERMIT_PASSWORD
  4. GitHub 个人令牌        ECO_MCP_SERVERS 内 github 条目 env
  5. 腾讯文档 Token         ECO_MCP_SERVERS 内 tencent_docs 条目 Authorization
  6. DeepSeek API Key       DEEPSEEK_API_KEY

安全约定:
  - 密码/Token 走 getpass：终端不回显、不进 shell 历史、不经聊天记录
  - 只写本仓库 .env（或 --env-file 指定），不打印明文（脱敏显示）
  - 写后立即复读校验；--check 只报告当前缺口（不动任何文件）

用法:
  python3 _scripts/setup_credentials.py            # 交互式选择
  python3 _scripts/setup_credentials.py --check    # 只报告缺口清单
  python3 _scripts/setup_credentials.py --item 2   # 直接进第 2 项
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ENV = ROOT / ".env"

ITEMS = {
    "1": {
        "title": "娄底市污染源在线监测系统",
        "fields": [
            ("WRYZXJC_USERNAME", "账号", False),
            ("WRYZXJC_PASSWORD", "密码", True),
        ],
    },
    "2": {
        "title": "国家四平台（综合执法监管）",
        "fields": [
            ("STHJZF_USERNAME", "账号", False),
            ("STHJZF_PASSWORD", "密码", True),
        ],
    },
    "3": {
        "title": "排污许可管理平台（内网）",
        "fields": [
            ("PERMIT_BASE", "主系统地址(如 http://内网IP/permit)", False),
            ("PERMIT_JGZF_BASE", "实施监管系统地址(如 http://内网IP)", False),
            ("PERMIT_JGZF_KEY", "实施监管系统签名密钥", True),
            ("PERMIT_USERNAME", "账号", False),
            ("PERMIT_PASSWORD", "密码", True),
        ],
    },
    "4": {"title": "GitHub 个人令牌（MCP）", "github_token": True},
    "5": {"title": "腾讯文档 Token（官方 MCP）", "tdocs_token": True},
    "6": {"title": "DeepSeek API Key", "ds_key": True},
}


def _mask(v: str) -> str:
    if not v:
        return "(空)"
    if len(v) <= 8:
        return v[:2] + "***"
    return v[:4] + "…" + v[-4:]


def _read_env(env_path: Path) -> dict[str, str]:
    """读取 .env 为键值字典（保留行序靠行号写回）。"""
    out: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _write_kv(env_path: Path, key: str, value: str) -> None:
    """按行写入/更新 key=value（值带引号防特殊字符破坏 .env 语法）。"""
    lines = env_path.read_text(encoding="utf-8").splitlines()
    found = False
    for i, line in enumerate(lines):
        if line.strip().startswith(f"{key}=") or line.strip().startswith(f"{key} "):
            lines[i] = f'{key}="{value}"'
            found = True
            break
    if not found:
        lines.append(f'{key}="{value}"')
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _servers(env_path: Path) -> tuple[list, int, list[str]]:
    """返回 (servers, 行号, 全部行)。"""
    lines = env_path.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        if line.strip().startswith("ECO_MCP_SERVERS="):
            raw = line.split("=", 1)[1].strip()
            try:
                return json.loads(raw), i, lines
            except json.JSONDecodeError as e:
                print(f"[错误] ECO_MCP_SERVERS 不是合法 JSON: {e}")
                sys.exit(2)
    return [], -1, lines


def _save_servers(env_path: Path, servers: list, idx: int, lines: list[str]) -> None:
    new_raw = json.dumps(servers, ensure_ascii=False, separators=(",", ":"))
    if idx >= 0:
        lines[idx] = "ECO_MCP_SERVERS=" + new_raw
    else:
        lines.append("ECO_MCP_SERVERS=" + new_raw)
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _set_github_token(env_path: Path, token: str) -> None:
    servers, idx, lines = _servers(env_path)
    for s in servers:
        if isinstance(s, dict) and s.get("name") == "github":
            s.setdefault("env", {})["GITHUB_PERSONAL_ACCESS_TOKEN"] = token
            break
    else:
        servers.append({"name": "github", "transport": "stdio",
                        "command": ["node", "github-server-dist"], "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": token}})
    _save_servers(env_path, servers, idx, lines)


def _set_tdocs_token(env_path: Path, token: str) -> None:
    from _scripts.setup_tencent_docs import set_token as tdocs_set  # noqa: E402 本地脚本复用
    tdocs_set(env_path, token)


def _set_ds_key(env_path: Path, key: str) -> None:
    _write_kv(env_path, "DEEPSEEK_API_KEY", key)


def check(env_path: Path) -> dict:
    """缺口清单（不发起网络请求，只看配置是否齐）。"""
    env = _read_env(env_path)
    servers, _, _ = _servers(env_path)
    gh = next((s for s in servers if isinstance(s, dict) and s.get("name") == "github"), {})
    td = next((s for s in servers if isinstance(s, dict) and s.get("name") == "tencent_docs"), {})

    def has(k):
        return bool((env.get(k) or "").strip())

    def server_env(k):
        return bool((gh.get("env") or {}).get(k, "").strip())

    def td_token():
        t = (td.get("headers") or {}).get("Authorization", "")
        return bool(t) and "PASTE_TOKEN_HERE" not in t

    rows = [
        ("LLM/DeepSeek Key", has("DEEPSEEK_API_KEY"), "DEEPSEEK_API_KEY"),
        ("在线监测-凭证", has("WRYZXJC_USERNAME") and has("WRYZXJC_PASSWORD"), "WRYZXJC_USERNAME/PASSWORD"),
        ("国家四平台-凭证", has("STHJZF_USERNAME") and has("STHJZF_PASSWORD"), "STHJZF_USERNAME/PASSWORD"),
        ("排污许可-内网地址", has("PERMIT_BASE") and has("PERMIT_JGZF_BASE"), "PERMIT_BASE/JGZF_BASE"),
        ("排污许可-凭证", has("PERMIT_USERNAME") and has("PERMIT_PASSWORD"), "PERMIT_USERNAME/PASSWORD"),
        ("GitHub Token", server_env("GITHUB_PERSONAL_ACCESS_TOKEN"), "github MCP env"),
        ("腾讯文档 Token", td_token(), "tencent_docs MCP Authorization"),
    ]
    missing = [f"({i + 1}) {name}" for i, (name, ok, _) in enumerate(rows) if not ok]
    return {"rows": [{"name": n, "ok": o, "loc": l} for n, o, l in rows],
            "missing": missing,
            "summary": f"配置完整度 {sum(1 for _, o, _ in rows if o)}/{len(rows)}"}


def run_interactive(env_path: Path, item: str | None = None) -> None:
    while True:
        print("\n═══ eco-agent 凭证本机自助配置 ═══")
        for k, v in ITEMS.items():
            print(f"  {k}. {v['title']}")
        print("  c. 查看当前缺口清单")
        print("  q. 退出")
        try:
            choice = item or input("选择 (1-6/c/q): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            # 无交互终端（管道/代理执行环境）：getpass 无法安全读取密码，
            # 直接退出并提示——凭证必须在本机真实终端里输入（不回显机制依赖终端）
            print("\n[提示] 本命令需要在**你自己的终端窗口**里运行（密码/Token 输入需要"
                  "真实终端的不回显机制，且凭证不应经过聊天/管道传递）。")
            return
        item = None
        if choice == "q":
            return
        if choice == "c":
            print(json.dumps(check(env_path), ensure_ascii=False, indent=1))
            continue
        if choice not in ITEMS:
            print("[提示] 无效选择")
            continue
        spec = ITEMS[choice]
        print(f"\n── {spec['title']} ──")
        if choice in ("4", "5", "6"):
            secret = getpass.getpass("粘贴（输入不回显，粘贴后回车）: ").strip()
            if not secret:
                print("[取消] 未输入，跳过。")
                continue
            if choice == "4":
                _set_github_token(env_path, secret)
            elif choice == "5":
                _set_tdocs_token(env_path, secret)
            else:
                _set_ds_key(env_path, secret)
            print(f"[完成] 已写入 {env_path}（脱敏: {_mask(secret)}）")
            continue
        for key, label, is_secret in spec["fields"]:
            if is_secret:
                val = getpass.getpass(f"{label}: ").strip()
            else:
                val = input(f"{label}: ").strip()
            if not val:
                print(f"[跳过] {key} 未输入，保持原值。")
                continue
            _write_kv(env_path, key, val)
            print(f"[完成] {key} = {_mask(val) if is_secret else val}")
        print("[完成] 本项配置结束。重启服务后生效（告诉我'已配置'我来重启）。")


def main() -> None:
    ap = argparse.ArgumentParser(description="eco-agent 凭证本机自助配置")
    ap.add_argument("--env-file", default=str(DEFAULT_ENV))
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--item", default=None)
    args = ap.parse_args()
    env_path = Path(args.env_file)
    if args.check:
        print(json.dumps(check(env_path), ensure_ascii=False, indent=1))
        return
    run_interactive(env_path, args.item)


if __name__ == "__main__":
    main()
