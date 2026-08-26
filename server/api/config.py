"""server/api/config.py — 模型配置读写 API（Web 设置页「模型配置」）

对标 DSH 的 settings-models：允许在 Web UI 选择 provider / 模型、填 API Key、
改 Base URL，写入 ~/.eco/.env 并热生效（os.environ 即时覆盖，进程无需重启）。
铁律：不回传明文 key（仅 has_key / 掩码）；密钥走 .env 为项目约定。
"""
import logging
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger("eco.config")

router = APIRouter()

ENV_FILE = Path.home() / ".eco" / ".env"


def _read_env_file(path: Path | None = None) -> dict:
    p = path or ENV_FILE
    env: dict = {}
    if p.exists():
        try:
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
        except OSError:
            pass
    return env


def _write_env_key(key: str, value: str, path: Path | None = None) -> None:
    """更新/追加 ~/.eco/.env 中的 key=value，保留其他行与注释"""
    p = path or ENV_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    lines = p.read_text(encoding="utf-8").splitlines() if p.exists() else []
    out: list[str] = []
    done = False
    for line in lines:
        if line.strip().startswith(f"{key}=") or line.strip().startswith(f"{key} ="):
            out.append(f"{key}={value}")
            done = True
        else:
            out.append(line)
    if not done:
        out.append(f"{key}={value}")
    p.write_text("\n".join(out) + "\n", encoding="utf-8")


def _mask(v: str) -> str:
    if not v:
        return ""
    if len(v) <= 8:
        return "****"
    return v[:4] + "****" + v[-4:]


@router.get("/config/model")
async def get_model_config() -> dict:
    """返回当前模型配置（含 provider 清单与 key 存在性；key 不落明文）"""
    import os

    from agent_core.llm_providers import list_providers

    env = _read_env_file()
    merged = dict(env)
    merged.update({k: v for k, v in os.environ.items() if v})

    provider = (merged.get("ECO_PROVIDER") or merged.get("ECO_LLM_PROVIDER") or "deepseek")
    specs = list_providers()
    providers = []
    for spec in specs:
        key = merged.get(spec.env_key, "") or (spec.name == "moonshot" and merged.get("KIMI_API_KEY") or "")
        providers.append({
            "name": spec.name,
            "display": spec.display,
            "base_url": spec.base_url,
            "default_model": spec.default_model,
            "models": spec.models,
            "has_key": bool(key),
            "env_key": spec.env_key,
        })
    active = next((p for p in providers if p["name"] == provider), None)
    model = merged.get("ECO_MODEL") or (active or {}).get("default_model") or ""
    # 明文 key 只在「本机修改密码框需要回显确认」时用——这里仅返回掩码
    active_key_env = (active or {}).get("env_key", "")
    api_key_masked = _mask(merged.get(active_key_env, "")) if active_key_env else ""
    base_url = merged.get("DEEPSEEK_BASE_URL") or (active or {}).get("base_url") or ""
    return {
        "provider": provider,
        "model": model,
        "base_url": base_url,
        "api_key_masked": api_key_masked,
        "api_key_env": active_key_env,
        "providers": providers,
    }


class ModelConfigBody(BaseModel):
    provider: str = ""
    model: str = ""
    api_key: str = ""      # 留空 = 保持不变
    base_url: str = ""     # 留空 = 保持不变


@router.post("/config/model")
async def save_model_config(body: ModelConfigBody) -> dict:
    """保存模型配置：写入 ~/.eco/.env 并热生效（os.environ 即时覆盖）"""
    import os

    from agent_core.llm_providers import get_provider

    spec = get_provider(body.provider) if body.provider else None
    if body.provider and spec is None:
        return {"ok": False, "error": f"未知 provider: {body.provider}"}

    changes: dict[str, str] = {}
    if body.provider:
        changes["ECO_PROVIDER"] = body.provider
    if body.model:
        changes["ECO_MODEL"] = body.model
    if body.base_url:
        changes["DEEPSEEK_BASE_URL"] = body.base_url if spec is None or spec.name == "deepseek" \
            else f"{spec.name.upper()}_BASE_URL"
    if body.api_key:
        key_env = spec.env_key if spec else "DEEPSEEK_API_KEY"
        if spec and spec.name == "moonshot":
            key_env = "MOONSHOT_API_KEY"
        changes[key_env] = body.api_key

    # 1) 热生效：先写 os.environ（当前进程立即生效，llm_client 每次请求读取）
    for k, v in changes.items():
        os.environ[k] = v

    # 2) 持久化到 ~/.eco/.env（尽力而为：环境写保护等失败时仅告警，不阻断热生效）
    persist_error = ""
    try:
        for k, v in changes.items():
            _write_env_key(k, v)
    except OSError as e:
        persist_error = f"写入 ~/.eco/.env 失败（本次会话已热生效，重启后需重新配置）: {e}"

    return {
        "ok": True,
        "applied": {k: (_mask(v) if "KEY" in k or "SECRET" in k else v) for k, v in changes.items()},
        "note": "已热生效" + ("；" + persist_error if persist_error else ""),
        "persist_warning": persist_error or "",
    }
