"""
envboot.py — 进程级环境引导（单一权威入口）

把仓库 .env 与 ~/.eco/.env 合入 os.environ（已存在的环境变量优先，不覆盖）。
llm_client 用私有 _env、mcp_connector 只读 os.environ——历史割裂导致
"仓库 .env 配了 MCP 但服务器进程看不到"类问题，统一由本模块在进程启动时收口。

空值遮蔽修复（2026-08-23）：python-dotenv 的 override=False 认为"已存在的键"
（哪怕值是空字符串）就跳过补填——进程环境里残留的 `DEEPSEEK_API_KEY=`
（空值，常见于 GUI 启动器/非登录 shell）会遮蔽 .env 里的真实密钥，
导致 "no api key (provider not configured)"。本模块对空值键做二次补填。

用法（server 工厂 / CLI 入口首行）：
    from agent_core.envboot import load_env_into_process
    load_env_into_process()
"""

from __future__ import annotations

import os
from pathlib import Path


def _parse_env_file(path: Path) -> dict[str, str]:
    """极简 .env 解析（dotenv 之外独立实现，便于空值补填与诊断）。
    只支持 KEY=VALUE 与 # 注释；值可带双/单引号。"""
    out: dict[str, str] = {}
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return out
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if key:
            out[key] = value
    return out


def _fill_empty_keys(parsed: list[dict[str, str]]) -> int:
    """空值遮蔽修复核心：环境里"存在但为空"的键视为缺失，
    按 parsed 顺序（仓库 .env 优先、~/.eco/.env 次之）用非空值补填。
    返回补填的键数；真实非空环境变量永远不被覆盖。"""
    filled = 0
    for key in _all_keys(parsed):
        current = os.environ.get(key, "")
        if current.strip():
            continue  # 已有非空值：保持原样
        for values in parsed:
            v = values.get(key, "")
            if v.strip():
                os.environ[key] = v
                filled += 1
                break
    return filled


def load_env_into_process() -> None:
    """合入两级 .env（真实非空环境变量优先，空值视为缺失并补填）。幂等。
    测试进程（PYTEST_CURRENT_TEST 存在）跳过——单测依赖 conftest 的
    环境隔离（剥离 *_API_KEY、临时 HOME），进程级引导会污染后续用例。"""
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover
        return
    repo_env = Path(__file__).resolve().parent.parent / ".env"
    user_env = Path.home() / ".eco" / ".env"
    # 第一层：dotenv 标准合入（真实环境变量优先）
    if repo_env.exists():
        load_dotenv(repo_env, override=False)
    if user_env.exists():
        load_dotenv(user_env, override=False)
    # 第二层：空值遮蔽修复（真实非空环境变量不被覆盖，语义不变）
    _fill_empty_keys([_parse_env_file(p) if p.exists() else {} for p in (repo_env, user_env)])


def _all_keys(parsed: list[dict[str, str]]) -> list[str]:
    seen: list[str] = []
    for values in parsed:
        for k in values:
            if k not in seen:
                seen.append(k)
    return seen
