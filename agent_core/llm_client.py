#!/usr/bin/env python3
"""
llm_client.py — Eco Agent 统一 LLM 调用层（Kimi / Moonshot OpenAI 兼容端点）

特性：
  - httpx 直连 https://api.moonshot.cn/v1/chat/completions，30s 超时
  - 指数退避重试（≤3 次）
  - 主模型失败自动切换备用模型 moonshot-v1-8k
  - 连续失败熔断 60s
  - 思考模型返回空内容时放大 max_tokens 重试（不计入熔断）
  - k2.x 系列仅接受 temperature=1，按 400 报错自适应并缓存该约束
  - 自动解析 .env；ECO_LLM_DISABLE=1 一键禁用
  - 进程级单例 get_default_client()
"""

import os
import time
import logging
import threading
from pathlib import Path

logger = logging.getLogger("llm_client")

ROOT = Path(__file__).resolve().parent.parent

DEFAULT_BASE_URL = "https://api.moonshot.cn/v1"
DEFAULT_MODEL = "kimi-k2.5"
FALLBACK_MODEL = "moonshot-v1-8k"
MAX_RETRIES = 3
TIMEOUT = 30.0
CIRCUIT_BREAK_SECONDS = 60


def _load_dotenv() -> None:
    """自动加载 .env（不覆盖已有环境变量）"""
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    try:
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v
    except Exception as e:
        logger.warning(f"[LLM] .env 解析失败: {e}")


_load_dotenv()


class LLMClient:
    """OpenAI 兼容端点 LLM 客户端"""

    def __init__(self, api_key: str = "", base_url: str = "", model: str = "",
                 fallback_model: str = FALLBACK_MODEL):
        self.api_key = api_key or os.environ.get("KIMI_API_KEY", "")
        self.base_url = (base_url or os.environ.get("KIMI_BASE_URL", DEFAULT_BASE_URL)).rstrip("/")
        self.model = model or os.environ.get("KIMI_MODEL", DEFAULT_MODEL)
        self.fallback_model = fallback_model
        self._disabled = os.environ.get("ECO_LLM_DISABLE", "") == "1"
        self._fail_count = 0
        self._circuit_open_until = 0.0
        self._temp_one_only = False  # k2.x 仅接受 temperature=1
        self._lock = threading.Lock()

    def available(self) -> bool:
        if self._disabled:
            return False
        if not self.api_key:
            return False
        return time.time() >= self._circuit_open_until

    def _on_failure(self) -> None:
        with self._lock:
            self._fail_count += 1
            if self._fail_count >= MAX_RETRIES:
                self._circuit_open_until = time.time() + CIRCUIT_BREAK_SECONDS
                logger.warning(f"[LLM] 连续失败 {self._fail_count} 次，熔断 {CIRCUIT_BREAK_SECONDS}s")

    def _on_success(self) -> None:
        with self._lock:
            self._fail_count = 0
            self._circuit_open_until = 0.0

    def chat(self, messages: list[dict[str, str]], max_tokens: int = 512,
             temperature: float = 0.7, model: str = "") -> str | None:
        """调用 chat/completions，失败返回 None"""
        if not self.available():
            return None
        try:
            import httpx
        except ImportError:
            logger.warning("[LLM] httpx 未安装，LLM 不可用")
            return None

        use_model = model or self.model
        if self._temp_one_only:
            temperature = 1

        last_err = None
        for attempt in range(1, MAX_RETRIES + 1):
            cur_model = use_model if attempt < MAX_RETRIES else (self.fallback_model or use_model)
            payload = {
                "model": cur_model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            try:
                resp = httpx.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=payload, timeout=TIMEOUT,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    content = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
                    if not content.strip():
                        # 思考模型空内容：放大 max_tokens 重试一次，不计熔断
                        if max_tokens < 2048:
                            logger.info("[LLM] 返回空内容，放大 max_tokens 重试（不计熔断）")
                            return self.chat(messages, max_tokens=2048, temperature=temperature, model=cur_model)
                        logger.warning("[LLM] 返回空内容且已达最大 max_tokens")
                        return None
                    self._on_success()
                    return content.strip()
                # 4xx 特殊处理
                if resp.status_code == 400 and "temperature" in resp.text:
                    logger.info(f"[LLM] 模型 {cur_model} 仅接受 temperature=1，自适应")
                    self._temp_one_only = True
                    temperature = 1
                    continue
                if resp.status_code == 404 and cur_model != self.fallback_model and self.fallback_model:
                    logger.warning(f"[LLM] 模型 {cur_model} 404，切换备用模型 {self.fallback_model}")
                    use_model = self.fallback_model
                    continue
                last_err = f"HTTP {resp.status_code}: {resp.text[:200]}"
                logger.warning(f"[LLM] 第{attempt}次调用失败: {last_err}")
                if 400 <= resp.status_code < 500:
                    break  # 客户端错误不重试（除上面已处理的）
            except Exception as e:
                last_err = str(e)
                logger.warning(f"[LLM] 第{attempt}次调用异常: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(2 ** (attempt - 1))  # 指数退避 1s, 2s
        self._on_failure()
        return None

    def complete(self, prompt: str, system: str = "", **kw) -> str | None:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return self.chat(messages, **kw)


_default_client: LLMClient | None = None
_default_lock = threading.Lock()


def get_default_client() -> LLMClient:
    """进程级单例"""
    global _default_client
    with _default_lock:
        if _default_client is None:
            _default_client = LLMClient()
    return _default_client
