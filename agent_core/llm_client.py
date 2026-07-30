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
import os, time, logging, json
from pathlib import Path
from typing import Optional

# 抑制 httpx 的 HTTP Request 日志输出
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.basicConfig(level=logging.WARNING, format="%(message)s")
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

    def complete(self, prompt: str, system: str = "", max_tokens: int = 512) -> str:
        """Complete interface expected by ReAct++ (L1 micro-action loop)
        
        Args:
            prompt: User message text
            system: System prompt text
            max_tokens: Max tokens for response
        Returns:
            Response text string, or empty string on failure
        """
        if not self.available():
            logger.warning("[complete] LLM unavailable")
            return ""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        try:
            resp = self._httpx.post(
                f"{self._provider['base_url']}/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                json={"model": self._provider["default_model"], "messages": messages,
                       "temperature": 0.7, "max_tokens": max_tokens, "stream": False},
                timeout=30,
            )
            if resp.status_code == 200:
                data = resp.json()
                text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                return text.strip()
            logger.warning(f"[complete] HTTP {resp.status_code}")
            return ""
        except Exception as e:
            logger.warning(f"[complete] {e}")
            return ""

    def chat(self, messages: list, model: str = "", stream: bool = False, temperature: float = 0.7) -> dict:
        """OpenAI-compatible chat completions"""
        if not self.available():
            return {"choices": [{"message": {"content": "[LLM unavailable: Run: eco setup]"}}]}
        if not model:
            model = self._provider["default_model"]
        start = time.time()
        self._stats["calls"] += 1
        result = self._call_api(messages, model, temperature)
        if result and not result.get("_error"):
            self._stats["total_elapsed_s"] += time.time() - start
            return result
        result = self._call_kimi_fallback(messages, model, temperature)
        if result and not result.get("_error"):
            self._stats["total_elapsed_s"] += time.time() - start
            return result
        self._stats["errors"] += 1
        self._stats["total_elapsed_s"] += time.time() - start
        return {"choices": [{"message": {"content": "[LLM unavailable: all backends failed]"} }]}

    def _call_api(self, messages, model, temp) -> Optional[dict]:
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
            return {"_error": True}
        except Exception as e:
            return {"_error": True}

    def chat_stream(self, messages: list, on_chunk=None) -> str:
        """Streaming chat — yields chunks via callback, returns full text
        on_chunk(chunk_text: str) is called for each content chunk
        """
        if not self.available():
            if on_chunk: on_chunk("[LLM not configured. Run: eco setup]")
            return ""
        model = self._provider["default_model"]
        full_text = ""
        try:
            with self._httpx.stream(
                "POST",
                f"{self._provider['base_url']}/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                json={"model": model, "messages": messages, "temperature": 0.7, "stream": True},
                timeout=120,
            ) as resp:
                _last_chunk = ""
                for line in resp.iter_lines():
                    if line:
                        line = line.decode('utf-8') if isinstance(line, bytes) else line
                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str.strip() == "[DONE]":
                                break
                            try:
                                data = json.loads(data_str)
                                delta = data.get("choices", [{}])[0].get("delta", {})
                                chunk = delta.get("content", "")
                                # Dedup: DeepSeek SSE sometimes resends the same chunk
                                if chunk and chunk != _last_chunk:
                                    _last_chunk = chunk
                                    full_text += chunk
                                    if on_chunk: on_chunk(chunk)
                            except json.JSONDecodeError:
                                pass
        except Exception as e:
            err = "[Stream error: " + str(e) + "]"
            full_text += err
            if on_chunk: on_chunk(err)
        if not full_text and on_chunk:
            r = self.chat(messages)
            text = r.get("choices", [{}])[0].get("message", {}).get("content", "")
            if on_chunk: on_chunk(text)
            return text
        return full_text

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
        r = c.complete("Say hello in 3 words", system="You are helpful.")
        print(f"[OK] complete(): {r}")
        r2 = c.chat([{"role":"user","content":"Say hello in 5 words"}])
        t = r2.get("choices",[{}])[0].get("message",{}).get("content","")
        print(f"[OK] chat(): {t}")
        print(f"[OK] Stats: {c.get_stats()}")
    else:
        print("[!] LLM not available, run: eco setup")
