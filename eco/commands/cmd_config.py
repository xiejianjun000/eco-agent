#!/usr/bin/env python3
"""cmd_config.py - eco config 子命令

用法：
  eco config show|get|set|init|path          配置文件（~/.eco/.env）管理
  eco config model list                      表格列出全部 provider（有 key 的标 ✅）
  eco config model use <name>                写入 ECO_LLM_PROVIDER 到配置文件
  eco config model test [name]               发一条 "ping" 验证连通（无 key 清晰报错）

铁律：只读写 ~/.eco/.env，绝不把 key 打印到终端；本文件不含任何真实 key。
"""
import os
from pathlib import Path

ENV_FILE = Path.home() / ".eco" / ".env"

# 不允许写入配置文件的键（防止误存真实密钥到非 env 占位之外的位置无限制——
# 这里不拦截，密钥走 .env 本就是本项目约定；仅提示勿提交）


def _read_env_file(path: Path | None = None) -> dict:
    p = path or ENV_FILE
    env = {}
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def _write_env_key(key: str, value: str, path: Path | None = None) -> None:
    """更新/追加 ~/.eco/.env 中的 key=value，保留其他行与注释"""
    p = path or ENV_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    lines = p.read_text(encoding="utf-8").splitlines() if p.exists() else []
    out, done = [], False
    for line in lines:
        if line.strip().startswith(f"{key}=") or line.strip().startswith(f"{key} ="):
            out.append(f"{key}={value}")
            done = True
        else:
            out.append(line)
    if not done:
        out.append(f"{key}={value}")
    p.write_text("\n".join(out) + "\n", encoding="utf-8")


def _merged_env() -> dict:
    """os.environ 覆盖 ~/.eco/.env（与 llm_client 读取口径一致：环境变量优先）"""
    env = _read_env_file()
    merged = dict(env)
    merged.update(os.environ)
    return merged


def _mask(v: str) -> str:
    if not v:
        return ""
    if len(v) <= 8:
        return "****"
    return v[:4] + "****" + v[-4:]


# ---------------------------------------------------------------------------
# model 子命令（SPEC 模块 A）
# ---------------------------------------------------------------------------
def _model_list() -> int:
    from agent_core.llm_providers import list_providers
    env = _merged_env()
    rows = []
    for spec in list_providers():
        if spec.name == "custom":
            has = bool(env.get("ECO_CUSTOM_BASE_URL"))
        elif spec.name == "ollama":
            has = True  # 本地 provider 无需 key
        else:
            has = spec.has_key(env) or (spec.name == "moonshot" and bool(env.get("KIMI_API_KEY")))
        base = spec.base_url or "(ECO_CUSTOM_BASE_URL)"
        rows.append((spec.name, spec.display, base, spec.default_model or "-",
                     "✅" if has else "❌"))
    headers = ("NAME", "显示名", "BASE URL", "默认模型", "KEY")
    widths = [max(len(str(r[i])) for r in rows + [headers]) for i in range(5)]
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    print(fmt.format(*headers))
    print(fmt.format(*["-" * w for w in widths]))
    for r in rows:
        print(fmt.format(*r))
    print("\n用法: eco config model use <name>  |  eco config model test [name]")
    return 0


def _model_use(name: str | None) -> int:
    if not name:
        print("用法: eco config model use <name>")
        return 2
    from agent_core.llm_providers import get_provider
    try:
        spec = get_provider(name)
    except KeyError as e:
        print(e.args[0])
        return 2
    _write_env_key("ECO_LLM_PROVIDER", spec.name)
    print(f"已切换默认 provider: {spec.name}（{spec.display}）")
    print(f"配置文件: {ENV_FILE}  (ECO_LLM_PROVIDER={spec.name})")
    if spec.name == "custom":
        print("请同时在配置文件或环境中设置 ECO_CUSTOM_BASE_URL / ECO_CUSTOM_API_KEY / ECO_CUSTOM_MODEL")
    elif spec.name != "ollama" and not spec.has_key(_merged_env()):
        print(f"提示: 尚未检测到 {spec.env_key}，请设置后使用（申请入口: {spec.doc or '见官方文档'}）")
    return 0


def _model_test(name: str | None) -> int:
    from agent_core.llm_providers import get_provider, resolve_provider
    env = _merged_env()
    try:
        spec = get_provider(name) if name else resolve_provider(None, env)
    except KeyError as e:
        print(e.args[0])
        return 2
    has_key = (spec.has_key(env)
               or (spec.name == "moonshot" and bool(env.get("KIMI_API_KEY")))
               or spec.name == "ollama")
    if spec.name == "custom" and not env.get("ECO_CUSTOM_BASE_URL"):
        print("[model test] custom provider 未配置 ECO_CUSTOM_BASE_URL")
        return 1
    if not has_key:
        print(f"[model test] 未检测到 {spec.env_key}，无法测试 {spec.name}。"
              f"请先设置该环境变量（申请入口: {spec.doc or '见官方文档'}）")
        return 1
    from agent_core.llm_client import LLMClient
    client = LLMClient.from_provider(spec.name)
    print(f"[model test] {spec.name} ({spec.display}) → {client._provider['base_url']}"
          f"  model={client._provider['default_model']}  key={_mask(client._api_key)}")
    text = client.complete("ping", system="Reply with a short greeting.",
                           max_tokens=16, timeout=30.0)
    if text:
        print(f"[model test] ✅ 连通正常，响应: {text[:120]}")
        return 0
    detail = LLMClient._friendly_error(client.last_error)
    print(f"[model test] ❌ 调用失败: {detail}")
    return 1


def run(args) -> int:
    action = getattr(args, "action", None) or "show"
    key = getattr(args, "key", None)
    value = getattr(args, "value", None)

    if action == "model":
        sub = (key or "list").lower()
        if sub == "list":
            return _model_list()
        if sub == "use":
            return _model_use(value)
        if sub == "test":
            return _model_test(value)
        print(f"未知 model 子命令: {sub}（可用: list / use / test）")
        return 2

    if action == "path":
        print(ENV_FILE)
        return 0
    if action == "show":
        env = _read_env_file()
        if not env:
            print(f"(空) 配置文件: {ENV_FILE}")
            return 0
        for k, v in env.items():
            shown = _mask(v) if ("KEY" in k or "SECRET" in k or "TOKEN" in k) else v
            print(f"{k}={shown}")
        return 0
    if action == "get":
        if not key:
            print("用法: eco config get <key>")
            return 2
        print(_read_env_file().get(key, ""))
        return 0
    if action == "set":
        if not key or value is None:
            print("用法: eco config set <key> <value>")
            return 2
        _write_env_key(key, value)
        print(f"已写入 {key}（{ENV_FILE}）")
        return 0
    if action == "init":
        if not ENV_FILE.exists():
            ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
            ENV_FILE.write_text("# eco Agent 配置（勿提交真实 key 到仓库）\n", encoding="utf-8")
            print(f"已创建 {ENV_FILE}")
        else:
            print(f"已存在 {ENV_FILE}")
        return 0
    print(f"未知 action: {action}")
    return 2
