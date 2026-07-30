#!/usr/bin/env python3
"""llm_client.py - Unified LLM client for ECO AGENT

Architecture:
  eco chat/serve -> EcoLoops -> ReAct++ -> LLMClient -> Direct LLM API (OpenAI compat)
                                                     -> govmcp LLM Gateway (optional)
                                                     -> Kimi/Moonshot direct (fallback)

Reads config from ~/.eco/.env:
  ECO_PROVIDER=deepseek|openai|anthropic|kimi|qwen|doubao
  DEEPSEEK_API_KEY=sk-...
"""
import os, time, logging
from pathlib import Path
from typing import Optional

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("llm_client")

PROVIDERS = {
    "deepseek": {"base_url": "https://api.deepseek.com/v1", "api_key_env": "DEEPSEEK_API_KEY", "default_model": "deepseek-chat"},
    "openai": {"base_url": "https://api.openai.com/v1", "api_key_env": "OPENAI_API_KEY", "default_model": "gpt-4o"},
    "anthropic": {"base_url": "https://api.anthropic.com/v1", "api_key_env": "ANTHROPIC_API_KEY", "default_model": "claude-sonnet-4-20250514"},
    "kimi": {"base_url": "https://api.moonshot.cn/v1", "api_key_env": "KIMI_API_KEY", "default_model": "kimi-k2.5"},
    "qwen": {"base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "api_key_env": "DASHSCOPE_API_KEY", "default_model": "qwen-max"},
    "doubao": {"base_url": "https://ark.cn-beijing.volces.com/api/v3", "api_key_env": "DOUBAO_API_KEY", "default_model": "doubao-pro-32k"},
}

class LLMClient:
    def __init__(self):
        env = {}
        env_file = Path.home() / ".eco" / ".env"
        if env_file.exists():
            for l in env_file.read_text().splitlines():
                if "=" in l:
                    k, v = l.split("=", 1)
                    env[k.strip()] = v.strip()
        self._env = env
        self._provider_name = os.environ.get("ECO_PROVIDER") or env.get("ECO_PROVIDER", "deepseek")
        prov = PROVIDERS.get(self._provider_name, PROVIDERS["deepseek"])
        self._provider = prov
        self._api_key = os.environ.get(prov["api_key_env"]) or env.get(prov["api_key_env"], "")
        self._stats = {"calls": 0, "errors": 0, "total_elapsed_s": 0.0}
        self._httpx = None
        try:
            import httpx; self._httpx = httpx
        except ImportError:
            logger.warning("httpx not installed")

    def available(self) -> bool:
        return self._httpx is not None and bool(self._api_key)

    def chat(self, messages: list, model: str = "", stream: bool = False, temperature: float = 0.7) -> dict:
        if not self.available():
            return {"choices": [{"message": {"content": "[LLM unavailable: Run: eco setup]"}}]}
        if not model:
            model = self._provider["default_model"]
        start = time.time()
        self._stats["calls"] += 1

        # Direct OpenAI-compatible API call (primary path)
        result = self._call_direct(messages, model, temperature)
        if result and not result.get("_error"):
            self._stats["total_elapsed_s"] += time.time() - start
            return result

        # Fallback: Kimi direct
        result = self._call_kimi_fallback(messages, model, temperature)
        if result and not result.get("_error"):
            self._stats["total_elapsed_s"] += time.time() - start
            return result

        self._stats["errors"] += 1
        self._stats["total_elapsed_s"] += time.time() - start
        return {"choices": [{"message": {"content": f"[LLM unavailable: all backends failed]"} }]}

    def _call_direct(self, messages, model, temp) -> Optional[dict]:
        if not self._httpx or not self._api_key:
            return None
        try:
            resp = self._httpx.post(
                f"{self._provider['base_url']}/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                json={"model": model, "messages": messages, "temperature": temp, "stream": False},
                timeout=60,
            )
            if resp.status_code == 200:
                return resp.json()
            logger.warning(f"[{self._provider_name}] HTTP {resp.status_code}")
            return {"_error": True}
        except Exception as e:
            logger.warning(f"[{self._provider_name}] {e}")
            return {"_error": True}

    def _call_kimi_fallback(self, messages, model, temp) -> Optional[dict]:
        kimi_key = os.environ.get("KIMI_API_KEY") or self._env.get("KIMI_API_KEY", "")
        if not self._httpx or not kimi_key:
            return None
        try:
            resp = self._httpx.post(
                "https://api.moonshot.cn/v1/chat/completions",
                headers={"Authorization": f"Bearer {kimi_key}"},
                json={"model": "kimi-k2.5", "messages": messages, "temperature": temp, "stream": False},
                timeout=30,
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return None

    def get_stats(self) -> dict:
        s = dict(self._stats)
        s["avg_elapsed_s"] = round(s["total_elapsed_s"] / max(s["calls"], 1), 2)
        s["provider"] = self._provider_name
        s["model"] = self._provider["default_model"]
        s["has_api_key"] = bool(self._api_key)
        return s

_client = None
def get_default_client() -> LLMClient:
    global _client
    if _client is None:
        _client = LLMClient()
    return _client

def chat(messages: list, **kwargs) -> dict:
    return get_default_client().chat(messages, **kwargs)

if __name__ == "__main__":
    import sys as _sys, io
    _sys.stdout = io.TextIOWrapper(_sys.stdout.buffer, encoding="utf-8", errors="replace")
    c = get_default_client()
    if c.available():
        r = c.chat([{"role":"user","content":"Say hello in 5 words"}])
        t = r.get("choices",[{}])[0].get("message",{}).get("content","[no response]")
        print(f"[OK] {t[:80]}")
    else:
        print(f"[?] Provider={c.get_provider_name() if hasattr(c,'get_provider_name') else c._provider_name} API_Key={c.available()}")
        print("[!] Run: eco setup")
    print(f"[OK] Stats: {c.get_stats()}")
