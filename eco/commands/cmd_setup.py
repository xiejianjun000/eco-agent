"""
eco setup — 交互式配置向导
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

log = logging.getLogger("eco.setup")
logging.basicConfig(level=logging.INFO, format="%(message)s")
ROOT = Path(__file__).resolve().parent.parent.parent


def run(args) -> int:
    quick = args.quick
    print("\n" + "=" * 50)
    print("  ECO AGENT Configuration Wizard")
    print("=" * 50 + "\n")

    provider, api_key = _step_provider(quick)
    config_dir = _ensure_config_dir()
    _write_env(config_dir, provider, api_key)
    _step_deps()
    if not quick:
        _step_platforms()

    print("\n" + "=" * 50)
    print("  ECO AGENT is ready!")
    print("=" * 50)
    print("\n  Quick start:")
    print("    eco chat              Interactive chat")
    print("    eco chat 'question'    One-shot query")
    print("    eco serve              Start API server")
    print("    eco mcp serve          Start MCP server")
    print("    eco doctor             Health check\n")
    return 0


def _step_provider(quick: bool):
    providers = {
        "1": ("deepseek", "DEEPSEEK_API_KEY", "DeepSeek (recommended)"),
        "2": ("openai", "OPENAI_API_KEY", "OpenAI (GPT-4o)"),
        "3": ("anthropic", "ANTHROPIC_API_KEY", "Anthropic (Claude)"),
    }
    if quick:
        for key, ek, _ in providers.values():
            if os.environ.get(ek) or _env_get(ek):
                return key, os.environ.get(ek) or _env_get(ek) or ""
        return "deepseek", ""
    print("Select LLM provider:")
    for k, (_, _, desc) in providers.items():
        print(f"  {k}. {desc}")
    c = input("\nChoice (1-3) [1]: ").strip() or "1"
    sel = providers.get(c, providers["1"])
    ak = os.environ.get(sel[1], "") or _env_get(sel[1]) or input(f"Enter {sel[2]} API Key (or skip): ").strip()
    return sel[0], ak


def _ensure_config_dir() -> Path:
    d = Path.home() / ".eco"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _env_get(key: str) -> str | None:
    ep = Path.home() / ".eco" / ".env"
    if not ep.exists():
        return None
    for line in ep.read_text().splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            if k.strip() == key:
                return v.strip()
    return None


def _write_env(config_dir: Path, provider: str, api_key: str):
    ep = config_dir / ".env"
    ek_map = {"deepseek": "DEEPSEEK_API_KEY", "openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}
    ek = ek_map.get(provider, "DEEPSEEK_API_KEY")
    env = {}
    if ep.exists():
        for line in ep.read_text().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    if api_key:
        env[ek] = api_key
    env["ECO_PROVIDER"] = provider
    ep.write_text("\n".join(f"{k}={v}" for k, v in env.items()) + "\n")
    log.info(f"Config written: {ep}")


def _step_deps():
    missing = []
    for m in ["httpx", "cryptography", "fastapi"]:
        try:
            __import__(m)
        except ImportError:
            missing.append(m)
    if missing:
        log.info(f"Missing deps: {', '.join(missing)}")
        log.info(f"Run: pip install {' '.join(missing)}")


def _step_platforms():
    print("\nMessaging platform config (optional): Feishu / WeCom / DingTalk / Telegram")
    print("Set env vars then run: eco gateway start\n")
