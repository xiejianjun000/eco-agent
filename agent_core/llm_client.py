#!/usr/bin/env python3
"""llm_client.py - Unified LLM client for ECO AGENT

Architecture:
  eco chat/serve -> EcoLoops -> ReAct++ -> LLMClient -> govmcp LLM Gateway (optional, GOVMCP_GATEWAY)
                                                     -> Direct LLM API (OpenAI compat, PROVIDERS)
                                                     -> Kimi/Moonshot direct (fallback)

Reads config from ~/.eco/.env:
  ECO_PROVIDER=deepseek|openai|anthropic|kimi|qwen|doubao
  DEEPSEEK_API_KEY=sk-...
  GOVMCP_GATEWAY=http://127.0.0.1:9000   (optional; OpenAI-compatible /v1/chat/completions)
  GOVMCP_GATEWAY_KEY=...                 (optional bearer token for the gateway)
  ECO_LLM_DISABLE=1                      (force offline / rule-mode degradation)
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

KIMI_BASE_URL = "https://api.moonshot.cn/v1"
KIMI_FALLBACK_MODEL = "kimi-k2.5"


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
        # govmcp LLM 网关（可选）：配置后优先走网关，失败降级 PROVIDERS 直连
        self._gateway_url = (os.environ.get("GOVMCP_GATEWAY") or env.get("GOVMCP_GATEWAY", "")).rstrip("/")
        self._gateway_key = os.environ.get("GOVMCP_GATEWAY_KEY") or env.get("GOVMCP_GATEWAY_KEY", "")
        self._stats = {"calls": 0, "errors": 0, "total_elapsed_s": 0.0}
        self._httpx = None
        try:
            import httpx; self._httpx = httpx
        except ImportError:
            logger.warning("httpx not installed")

    @staticmethod
    def _disabled() -> bool:
        return os.environ.get("ECO_LLM_DISABLE", "").strip().lower() in ("1", "true", "yes", "on")

    def available(self) -> bool:
        return self._httpx is not None and bool(self._api_key) and not self._disabled()

    @staticmethod
    def _resolve_temperature(model: str, temperature: float) -> float:
        """kimi-k2.x 系列只接受 temperature=1，按模型名前缀自适应强制"""
        if (model or "").lower().startswith("kimi-k2"):
            return 1
        return temperature

    def _build_payload(self, model: str, messages: list, temperature: float = 0.7,
                       max_tokens: int = 0, stream: bool = False, tools: list = None) -> dict:
        """单一 payload 构建入口：所有调用路径的温度自适应都在这里收敛"""
        payload = {"model": model, "messages": messages,
                   "temperature": self._resolve_temperature(model, temperature), "stream": stream}
        if max_tokens:
            payload["max_tokens"] = max_tokens
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        return payload

    def _post_chat(self, base_url: str, api_key: str, payload: dict, timeout: int = 60):
        """POST OpenAI 兼容 /chat/completions；返回 (dict|None, error_str|None)"""
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        try:
            resp = self._httpx.post(
                f"{base_url}/chat/completions", headers=headers, json=payload, timeout=timeout)
            if resp.status_code == 200:
                return resp.json(), None
            return None, f"HTTP {resp.status_code}: {getattr(resp, 'text', '')[:200]}"
        except Exception as e:
            return None, f"{type(e).__name__}: {e}"

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
        model = self._provider["default_model"]
        payload = self._build_payload(model, messages, temperature=0.7, max_tokens=max_tokens)
        data, err = self._post_chat(self._provider["base_url"], self._api_key, payload, timeout=30)
        if err:
            logger.warning(f"[complete] {err}")
            return ""
        return (data.get("choices", [{}])[0].get("message", {}).get("content", "") or "").strip()

    def chat(self, messages: list, model: str = "", stream: bool = False, temperature: float = 0.7) -> dict:
        """OpenAI-compatible chat completions.

        调用链：govmcp 网关（若配置 GOVMCP_GATEWAY）-> PROVIDERS 直连 -> Kimi 直连兜底。
        每级错误透传进错误链，最终失败时返回降级消息并携带 _error/_error_detail。
        """
        if self._disabled():
            return {"_error": True, "_error_detail": "disabled via ECO_LLM_DISABLE",
                    "choices": [{"message": {"content": "[LLM disabled]"}}]}
        if not self.available():
            return {"choices": [{"message": {"content": "[LLM unavailable: Run: eco setup]"}}]}
        if not model:
            model = self._provider["default_model"]
        start = time.time()
        self._stats["calls"] += 1
        errors = []
        result = None
        # 1) govmcp 网关优先（可选）
        if self._gateway_url:
            result, err = self._call_gateway(messages, model, temperature)
            if err:
                errors.append(f"gateway({self._gateway_url}): {err}")
                logger.warning(f"[chat] gateway failed, fallback to direct: {err}")
                result = None
        # 2) PROVIDERS 直连
        if result is None:
            result, err = self._call_api(messages, model, temperature)
            if err:
                errors.append(f"direct({self._provider_name}): {err}")
                result = None
        # 3) Kimi 直连兜底
        if result is None:
            result, err = self._call_kimi_fallback(messages, model, temperature)
            if err:
                errors.append(f"kimi_fallback: {err}")
                result = None
        self._stats["total_elapsed_s"] += time.time() - start
        if result is not None:
            return result
        self._stats["errors"] += 1
        detail = " | ".join(errors) or "no backend attempted"
        logger.warning(f"[chat] all backends failed: {detail}")
        return {"_error": True, "_error_detail": detail,
                "choices": [{"message": {"content": "[LLM unavailable: all backends failed]"}}]}

    def _call_gateway(self, messages, model, temp) -> tuple:
        """走 govmcp 网关的 OpenAI 兼容端点。返回 (dict|None, error|None)"""
        if not self._httpx:
            return None, "httpx not installed"
        payload = self._build_payload(model, messages, temperature=temp)
        return self._post_chat(self._gateway_url, self._gateway_key, payload, timeout=60)

    def _call_api(self, messages, model, temp) -> tuple:
        """PROVIDERS 直连。返回 (dict|None, error|None)"""
        if not self._httpx or not self._api_key:
            return None, "no api key or httpx missing"
        payload = self._build_payload(model, messages, temperature=temp)
        return self._post_chat(self._provider["base_url"], self._api_key, payload, timeout=60)

    def _call_kimi_fallback(self, messages, model, temp) -> tuple:
        """Kimi/Moonshot 直连兜底（provider 本身即 kimi 时跳过，避免重复请求）"""
        if self._provider_name == "kimi":
            return None, "skipped (primary provider is already kimi)"
        kimi_key = os.environ.get("KIMI_API_KEY") or self._env.get("KIMI_API_KEY", "")
        if not self._httpx or not kimi_key:
            return None, "no KIMI_API_KEY"
        payload = self._build_payload(KIMI_FALLBACK_MODEL, messages, temperature=temp)
        return self._post_chat(KIMI_BASE_URL, kimi_key, payload, timeout=30)

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
                json=self._build_payload(model, messages, temperature=0.7, stream=True),
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
            body = self._build_payload(model, current_messages, temperature=0.7, tools=tools)

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
        s["gateway"] = self._gateway_url or None
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
