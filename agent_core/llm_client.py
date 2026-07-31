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
import os
import time
import logging
import json
from pathlib import Path

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
        self._last_error: dict | None = None  # {"kind": "quota|http|network", "status": int|None, "detail": str}
        self._disabled = os.environ.get("ECO_LLM_DISABLE", "").strip().lower() in ("1", "true", "yes")
        self._gateway = os.environ.get("GOVMCP_GATEWAY", "").rstrip("/")
        self._gateway_key = os.environ.get("GOVMCP_GATEWAY_KEY", "")
        self._httpx = None
        try:
            import httpx; self._httpx = httpx
        except ImportError:
            logger.warning("httpx not installed")

    def available(self) -> bool:
        return not self._disabled and self._httpx is not None and bool(self._api_key)

    def complete(self, prompt: str, system: str = "", max_tokens: int = 512,
                 timeout: float = 90.0) -> str:
        """Complete interface expected by ReAct++ (L1 micro-action loop)

        Args:
            prompt: User message text
            system: System prompt text
            max_tokens: Max tokens for response
            timeout: HTTP timeout seconds (default 90s, ecobench 单题时限同步口径)
        Returns:
            Response text string, or empty string on failure.
            Failure details are recorded in self.last_error for quota/rate-limit detection.
        """
        self._last_error = None
        if not self.available():
            logger.warning("[complete] LLM unavailable")
            self._last_error = {"kind": "unavailable", "status": None, "detail": "no api key or httpx"}
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
                       "temperature": self._resolve_temperature(self._provider["default_model"], 0.7),
                       "max_tokens": max_tokens, "stream": False},
                timeout=timeout,
            )
            if resp.status_code == 200:
                data = resp.json()
                text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                return text.strip()
            body = resp.text[:300]
            logger.warning(f"[complete] HTTP {resp.status_code}: {body}")
            kind = "quota" if self._is_quota_error(resp.status_code, body) else "http"
            self._last_error = {"kind": kind, "status": resp.status_code, "detail": body}
            return ""
        except Exception as e:
            logger.warning(f"[complete] {e}")
            self._last_error = {"kind": "network", "status": None, "detail": str(e)[:300]}
            return ""

    @staticmethod
    def _is_quota_error(status: int, body: str = "") -> bool:
        """429 限流 / 402 欠费 / 余额不足类错误判定（触发备用 provider 切换）"""
        if status in (402, 429):
            return True
        b = (body or "").lower()
        return any(k in b for k in ("insufficient", "balance", "quota", "rate_limit",
                                    "rate limit", "欠费", "余额"))

    @property
    def last_error(self) -> dict | None:
        return self._last_error

    def switch_provider(self, name: str) -> bool:
        """切换备用 provider（deepseek <-> kimi），重建 provider 配置与密钥。
        返回是否切换成功（目标 provider 有可用密钥）。"""
        prov = PROVIDERS.get(name)
        if prov is None:
            return False
        key = os.environ.get(prov["api_key_env"]) or self._env.get(prov["api_key_env"], "")
        if not key:
            return False
        self._provider_name = name
        self._provider = prov
        self._api_key = key
        self._last_error = None
        logger.warning(f"[llm_client] switched to provider: {name}")
        return True

    @staticmethod
    def _resolve_temperature(model: str, temp: float) -> float:
        """kimi-k2.x 系列只接受 temperature=1，其余模型透传（前缀匹配，大小写不敏感）"""
        return 1 if (model or "").lower().startswith("kimi-k2") else temp

    def chat(self, messages: list, model: str = "", stream: bool = False, temperature: float = 0.7) -> dict:
        """OpenAI-compatible chat completions。
        后端链：GOVMCP 网关（若配置）→ provider 直连 → Kimi 直连兜底（非 kimi provider 时）。
        全部失败返回 {"_error": True, "_error_detail": 完整错误链}。"""
        if self._disabled:
            return {"_error": True, "_error_detail": "disabled(ECO_LLM_DISABLE)",
                    "choices": [{"message": {"content": "[LLM unavailable: disabled by ECO_LLM_DISABLE]"}}]}
        if not self.available():
            return {"_error": True, "_error_detail": "unavailable(no api key or httpx)",
                    "choices": [{"message": {"content": "[LLM unavailable: Run: eco setup]"}}]}
        if not model:
            model = self._provider["default_model"]
        start = time.time()
        self._stats["calls"] += 1
        errors: list[str] = []
        attempts = []
        if self._gateway:
            attempts.append(("gateway", self._call_gateway))
        attempts.append(("direct", self._call_api))
        if self._provider_name != "kimi":
            attempts.append(("kimi-fallback", self._call_kimi_fallback))
        for _kind, fn in attempts:
            result, err = fn(messages, model, temperature)
            if result is not None and not result.get("_error"):
                self._stats["total_elapsed_s"] += time.time() - start
                return result
            if err:
                errors.append(err)
        self._stats["errors"] += 1
        self._stats["total_elapsed_s"] += time.time() - start
        return {"_error": True, "_error_detail": "; ".join(errors),
                "choices": [{"message": {"content": "[LLM unavailable: all backends failed]"}}]}

    def _call_gateway(self, messages, model, temp) -> tuple:
        """GOVMCP LLM 网关；返回 (result, err)。err 形如 'gateway(url): HTTP 502'"""
        url = f"{self._gateway}/chat/completions"
        try:
            resp = self._httpx.post(
                url,
                headers={"Authorization": f"Bearer {self._gateway_key}", "Content-Type": "application/json"},
                json={"model": model, "messages": messages,
                      "temperature": self._resolve_temperature(model, temp), "stream": False},
                timeout=60,
            )
            if resp.status_code == 200:
                return resp.json(), None
            return None, f"gateway({self._gateway}): HTTP {resp.status_code}"
        except Exception as e:
            return None, f"gateway({self._gateway}): {type(e).__name__} {e}"

    def _call_api(self, messages, model, temp) -> tuple:
        """provider 直连；err 形如 'direct(deepseek): HTTP 500'"""
        if not self._httpx or not self._api_key:
            return None, f"direct({self._provider_name}): no api key"
        try:
            resp = self._httpx.post(
                f"{self._provider['base_url']}/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                json={"model": model, "messages": messages,
                      "temperature": self._resolve_temperature(model, temp), "stream": False},
                timeout=60,
            )
            if resp.status_code == 200:
                return resp.json(), None
            return None, f"direct({self._provider_name}): HTTP {resp.status_code}"
        except Exception as e:
            return None, f"direct({self._provider_name}): {type(e).__name__} {e}"

    def _call_kimi_fallback(self, messages, model, temp) -> tuple:
        """Kimi 直连兜底（仅非 kimi provider）；err 形如 'kimi-fallback(kimi): HTTP 500'"""
        kimi_key = os.environ.get("KIMI_API_KEY") or self._env.get("KIMI_API_KEY", "")
        if not self._httpx or not kimi_key:
            return None, "kimi-fallback(kimi): no api key"
        try:
            resp = self._httpx.post(
                "https://api.moonshot.cn/v1/chat/completions",
                headers={"Authorization": f"Bearer {kimi_key}"},
                json={"model": "kimi-k2.5", "messages": messages,
                      "temperature": self._resolve_temperature("kimi-k2.5", temp), "stream": False},
                timeout=60,
            )
            if resp.status_code == 200:
                return resp.json(), None
            return None, f"kimi-fallback(kimi): HTTP {resp.status_code}"
        except Exception as e:
            return None, f"kimi-fallback(kimi): {type(e).__name__} {e}"

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

    def chat_with_tools(self, messages: list, tools: list, on_chunk=None, max_tool_rounds: int = 5) -> str:
        """
        CLAUDE/CODEX/HERMES 风格 Agent 循环：
        1. 发送消息 + 工具定义给 LLM
        2. 如果 LLM 返回 tool_calls → 执行工具 → 追加结果 → 循环
        3. 如果 LLM 返回文本 → 流式输出 → 完成

        Args:
            messages: 对话消息列表 (system + user + history)
            tools: 工具定义列表 (OpenAI function calling 格式)
            on_chunk: 流式回调函数
            max_tool_rounds: 最大工具调用轮数
        Returns:
            最终回答文本
        """
        if not self.available():
            msg = "[LLM not configured]"
            if on_chunk: on_chunk(msg)
            return msg

        model = self._provider["default_model"]
        current_messages = list(messages)
        tool_results_displayed = [False]

        for _round_idx in range(max_tool_rounds + 1):
            # 调用 LLM
            body = {
                "model": model,
                "messages": current_messages,
                "temperature": 0.7,
                "stream": False,
            }
            if tools:
                body["tools"] = tools
                body["tool_choice"] = "auto"

            try:
                resp = self._httpx.post(
                    f"{self._provider['base_url']}/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                    json=body,
                    timeout=60,
                )
                if resp.status_code != 200:
                    err = f"[API Error: {resp.status_code}]"
                    if on_chunk: on_chunk(err)
                    return err

                data = resp.json()
                msg = data.get("choices", [{}])[0].get("message", {})

            except Exception as e:
                err = f"[Error: {e}]"
                if on_chunk: on_chunk(err)
                return err

            # 检查是否有 tool_calls
            tool_calls = msg.get("tool_calls")
            if tool_calls:
                # 显示工具调用信息（CLAUDE Code 风格）
                for tc in tool_calls:
                    fn_name = tc["function"]["name"]
                    try:
                        fn_args = json.loads(tc["function"]["arguments"])
                    except Exception:
                        fn_args = {}
                    args_str = "; ".join(f"{k}={v}" for k, v in fn_args.items())

                    if on_chunk and not tool_results_displayed[0]:
                        on_chunk(f"\n  → 正在查询 {fn_name}...\n")
                        tool_results_displayed[0] = True
                    elif on_chunk:
                        on_chunk(f"\n  → 调用 {fn_name}({args_str})\n")

                # 执行工具
                from agent_core.tools_registry import execute_tool
                import asyncio

                # 追加 assistant 消息（含 tool_calls）
                assistant_msg = {"role": "assistant", "content": msg.get("content") or None}
                # OpenAI 格式：tool_calls 在 assistant message 中
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["function"]["name"],
                            "arguments": tc["function"]["arguments"]
                        }
                    }
                    for tc in tool_calls
                ]
                current_messages.append(assistant_msg)

                # 执行每个工具并追加结果
                for tc in tool_calls:
                    tool_name = tc["function"]["name"]
                    try:
                        tool_args = json.loads(tc["function"]["arguments"])
                    except Exception:
                        tool_args = {}

                    tool_result = asyncio.run(execute_tool(tool_name, tool_args))

                    current_messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": tool_result
                    })

                continue  # 继续循环

            # 没有 tool_calls，有文本回答 → 流式输出
            content = msg.get("content", "")
            if not content:
                content = str(msg)

            if on_chunk:
                # 模拟流式输出（逐段展示）
                chunk_size = 20
                for i in range(0, len(content), chunk_size):
                    on_chunk(content[i:i+chunk_size])
                    import time
                    time.sleep(0.01)

            return content

        # 超过最大工具轮数
        fallback = "[工具调用次数过多，请简化问题]"
        if on_chunk: on_chunk(fallback)
        return fallback

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
    import sys as _sys
    import io
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
