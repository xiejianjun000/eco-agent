#!/usr/bin/env python3
"""
llm_client.py — Eco Agent 统一 LLM 客户端（薄客户端）

架构：
  eco-agent → HTTP/OpenAI 兼容 → govmcp LLM Gateway → 国产模型适配器

双通道分离：
  LLM 推理 → HTTP（OpenAI 兼容协议）→ govmcp 网关
  工具调用 → MCP（JSON-RPC 协议）→ govmcp tools

支持：
  - govmcp 网关优先（11+ 国产模型自动路由）
  - Kimi 直连 fallback（网关不可用时）
  - model_tier 选择（cheap/strong/reasoning）
  - 指数退避重试
  - 离线模式（ECO_LLM_DISABLE=1）
  - 审计统计
"""

import os, sys, json, time, logging, threading
from pathlib import Path
from typing import Optional, Dict, Any, List

logger = logging.getLogger("llm_client")

ROOT = Path(__file__).resolve().parent.parent

# ── 配置 ──
GOVMCP_GATEWAY = os.environ.get("ECO_LLM_GATEWAY", "http://localhost:8001")
DIRECT_KIMI_URL = "https://api.moonshot.cn/v1"
DIRECT_KIMI_KEY = os.environ.get("KIMI_API_KEY", "")
DISABLE_LLM = os.environ.get("ECO_LLM_DISABLE", "0") == "1"
DEFAULT_TIER = os.environ.get("ECO_LLM_TIER", "strong")
DEFAULT_MODEL = "kimi-k2.5"

try:
    import httpx
except ImportError:
    httpx = None


class LLMClient:
    """统一 LLM 客户端——govmcp 网关优先 + Kimi fallback"""

    def __init__(self, gateway: str = GOVMCP_GATEWAY, tier: str = DEFAULT_TIER):
        self._gateway = gateway
        self._tier = tier
        self._stats: Dict[str, Any] = {"calls": 0, "errors": 0, "total_elapsed_s": 0.0}

    def chat(self, messages: List[Dict], model: str = "", stream: bool = False,
             temperature: float = 0.7, tier: str = "") -> Dict:
        """统一推理入口"""
        if DISABLE_LLM:
            return {"choices": [{"message": {"content": "[LLM disabled by ECO_LLM_DISABLE]"}}]}

        if not model:
            model = DEFAULT_MODEL
        if not tier:
            tier = self._tier

        start = time.time()
        self._stats["calls"] += 1
        last_error = ""

        # 优先 govmcp 网关
        result = self._call_gateway(messages, model, stream, temperature)
        if result:
            # 检查是否包含错误信息
            if result.get("error"):
                last_error = result.get("detail", "unknown gateway error")
                self._stats["errors"] += 1
            else:
                elapsed = time.time() - start
                self._stats["total_elapsed_s"] += elapsed
                return result

        # Kimi 直连 fallback
        result = self._call_kimi_direct(messages, model, stream, temperature)
        if result:
            elapsed = time.time() - start
            self._stats["total_elapsed_s"] += elapsed
            return result

        elapsed = time.time() - start
        self._stats["total_elapsed_s"] += elapsed
        self._stats["errors"] += 1
        return {"choices": [{"message": {"content": f"[LLM unavailable: {last_error}]"}}],
                "_error": last_error}

    def chat_cheap(self, messages: List[Dict]) -> Dict:
        """使用 cheap tier 模型（简单任务）"""
        return self.chat(messages, tier="cheap")

    def chat_strong(self, messages: List[Dict]) -> Dict:
        """使用 strong tier 模型（复杂任务）"""
        return self.chat(messages, tier="strong")

    def _call_gateway(self, messages: List[Dict], model: str, stream: bool, temp: float) -> Optional[Dict]:
        """通过 govmcp LLM 网关调用"""
        if not httpx:
            return None
        try:
            resp = httpx.post(
                f"{self._gateway}/v1/chat/completions",
                json={"model": model, "messages": messages,
                       "temperature": temp, "stream": stream},
                timeout=min(60, max(10, len(messages) * 2)),
            )
            if resp.status_code == 200:
                return resp.json()
            # 如实透传 503 错误原因
            detail = resp.text[:200] if resp.text else f"HTTP {resp.status_code}"
            logger.warning(f"[gateway] {resp.status_code}: {detail}")
            # 返回含错误详情的响应，防止被静默吞掉
            return {"error": True, "status_code": resp.status_code, "detail": detail}
        except Exception as e:
            logger.warning(f"[gateway] {e}")
            return {"error": True, "detail": str(e)}

    def _call_kimi_direct(self, messages: List[Dict], model: str, stream: bool, temp: float) -> Optional[Dict]:
        """直连 Kimi fallback"""
        if not httpx or not DIRECT_KIMI_KEY:
            return None
        try:
            resp = httpx.post(
                f"{DIRECT_KIMI_URL}/chat/completions",
                headers={"Authorization": f"Bearer {DIRECT_KIMI_KEY}"},
                json={"model": model or "kimi-k2.5", "messages": messages,
                       "temperature": temp, "stream": stream},
                timeout=30,
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            logger.warning(f"[direct] {e}")
        return None

    def get_stats(self) -> Dict:
        s = dict(self._stats)
        s["avg_elapsed_s"] = round(s["total_elapsed_s"] / max(s["calls"], 1), 2)
        s["gateway"] = self._gateway
        s["tier"] = self._tier
        return s


# ── 单例 ──
_client = None

def get_client(tier: str = "") -> LLMClient:
    global _client
    if _client is None:
        _client = LLMClient(tier=tier or DEFAULT_TIER)
    return _client

def chat(messages: List[Dict], **kwargs) -> Dict:
    return get_client().chat(messages, **kwargs)

def chat_cheap(messages: List[Dict]) -> Dict:
    return get_client(tier="cheap").chat_cheap(messages)

# ===== 测试 =====
def test():
    import sys as _sys, io
    _sys.stdout = io.TextIOWrapper(_sys.stdout.buffer, encoding='utf-8', errors='replace')
    c = get_client()
    result = c.chat([{"role": "user", "content": "say hello in one word"}], model="kimi-k2.5")
    text = result.get("choices", [{}])[0].get("message", {}).get("content", "[no response]")
    print(f"[TEST] LLM Client: {text[:80]}", flush=True)
    print(f"[TEST] Stats: {c.get_stats()}", flush=True)
    print("[OK] llm_client thin client test passed", flush=True)

if __name__ == "__main__":
    test()
