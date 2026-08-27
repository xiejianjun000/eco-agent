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
import sys
import time
import logging
import json
from pathlib import Path

# 抑制 httpx 的 HTTP Request 日志输出
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.basicConfig(level=logging.WARNING, format="%(message)s")
logger = logging.getLogger("llm_client")

# SPEC 模块 A：全量 provider 注册表在 agent_core.llm_providers（15 个内置 provider）。
# 下方 PROVIDERS 为 llm_client 历史公开结构（含 embedding_model 字段），保持向后兼容；
# 重叠条目（deepseek/kimi/qwen/doubao）取值与注册表一致，由注册表单一事实源生成。
from agent_core.llm_providers import PROVIDERS as REGISTRY_PROVIDERS  # noqa: E402


def _legacy_entry(reg_name: str, api_key_env: str = "", embedding_model=None) -> dict:
    """从注册表 ProviderSpec 生成 llm_client 历史 provider 条目"""
    spec = REGISTRY_PROVIDERS[reg_name]
    return {"base_url": spec.base_url,
            "api_key_env": api_key_env or spec.env_key,
            "default_model": spec.default_model,
            "embedding_model": embedding_model}


PROVIDERS = {
    "deepseek": _legacy_entry("deepseek"),  # DeepSeek 无 embedding → 向量通道自动禁用
    "openai": {"base_url": "https://api.openai.com/v1", "api_key_env": "OPENAI_API_KEY", "default_model": "gpt-4o", "embedding_model": "text-embedding-3-small"},
    "anthropic": {"base_url": "https://api.anthropic.com/v1", "api_key_env": "ANTHROPIC_API_KEY", "default_model": "claude-sonnet-4-20250514", "embedding_model": None},
    "kimi": _legacy_entry("moonshot", api_key_env="KIMI_API_KEY", embedding_model="moonshot-v1-embedding"),
    "qwen": _legacy_entry("qwen", embedding_model="text-embedding-v3"),
    "doubao": _legacy_entry("doubao", api_key_env="DOUBAO_API_KEY"),  # 历史 env 名保持兼容；注册表用 ARK_API_KEY
}

STATS_FILE = Path.home() / ".eco" / "stats.jsonl"


def record_llm_stat(provider: str, model: str, latency_ms: float,
                    prompt_tokens=None, completion_tokens=None,
                    path: str = "", ok: bool = True):
    """每次 LLM 调用追加一条结构化统计到 ~/.eco/stats.jsonl（供 eco doctor 查看）。
    写入失败静默降级（沙箱/权限受限环境不得影响 LLM 调用主链路）。"""
    import datetime as _dt
    rec = {
        "ts": _dt.datetime.now().isoformat(timespec="seconds"),
        "provider": provider, "model": model, "path": path,
        "latency_ms": latency_ms,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "ok": ok,
    }
    try:
        STATS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with STATS_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass  # 统计属于观测辅助，落盘失败不影响主链路


def summarize_llm_stats(limit: int = 0, stats_file=None) -> dict:
    """汇总 stats.jsonl：调用数/错误数/总 tokens/平均延迟/按 provider 分组"""
    path = Path(stats_file) if stats_file else STATS_FILE
    recs = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    recs.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    if limit:
        recs = recs[-limit:]
    total = len(recs)
    errors = sum(1 for r in recs if not r.get("ok", True))
    ptoks = sum(r.get("prompt_tokens") or 0 for r in recs)
    ctoks = sum(r.get("completion_tokens") or 0 for r in recs)
    lats = [r.get("latency_ms") or 0 for r in recs]
    by_provider: dict = {}
    for r in recs:
        p = r.get("provider", "?")
        agg = by_provider.setdefault(p, {"calls": 0, "errors": 0, "prompt_tokens": 0, "completion_tokens": 0})
        agg["calls"] += 1
        agg["errors"] += 0 if r.get("ok", True) else 1
        agg["prompt_tokens"] += r.get("prompt_tokens") or 0
        agg["completion_tokens"] += r.get("completion_tokens") or 0
    return {
        "calls": total, "errors": errors,
        "prompt_tokens": ptoks, "completion_tokens": ctoks,
        "total_tokens": ptoks + ctoks,
        "avg_latency_ms": round(sum(lats) / max(total, 1), 1),
        "by_provider": by_provider,
        "stats_file": str(path),
    }


class LLMClient:
    def __init__(self):
        # 自举环境：无论谁在何时构造本客户端（含早于 create_app/envboot 的
        # 导入期路径、子代理进程、独立脚本），先把 .env 合入 os.environ——
        # 根治"no api key (provider not configured)"时序类缺陷。
        # envboot 幂等且测试进程内自动跳过，重复调用无副作用。
        try:
            from agent_core.envboot import load_env_into_process

            load_env_into_process()
        except Exception:  # noqa: BLE001 — 自举失败由 _refresh_key 诊断兜底
            pass
        env = {}
        try:
            env_file = Path.home() / ".eco" / ".env"
            if env_file.exists():
                for l in env_file.read_text().splitlines():
                    if "=" in l:
                        k, v = l.split("=", 1)
                        env[k.strip()] = v.strip()
        except OSError:
            pass  # 读取受限（沙箱等）时降级为纯 os.environ 模式
        self._env = env
        self._provider_name = (os.environ.get("ECO_PROVIDER") or os.environ.get("ECO_LLM_PROVIDER")
                               or env.get("ECO_PROVIDER") or env.get("ECO_LLM_PROVIDER") or "deepseek")
        prov = PROVIDERS.get(self._provider_name, PROVIDERS["deepseek"])
        self._provider = prov
        # 模型覆盖：ECO_MODEL 环境变量（如 deepseek-v4-pro）覆盖 provider 默认模型
        eco_model = os.environ.get("ECO_MODEL", "").strip()
        if eco_model:
            self._provider = dict(prov, default_model=eco_model)
        self._api_key = os.environ.get(prov["api_key_env"]) or env.get(prov["api_key_env"], "")
        self._stats = {"calls": 0, "errors": 0, "total_elapsed_s": 0.0}
        self._last_error: dict | None = None  # {"kind": "quota|http|network", "status": int|None, "detail": str}
        self._last_usage: dict = {}  # 最近一次调用的 usage（span 树 tokens 采集用）
        self._disabled = os.environ.get("ECO_LLM_DISABLE", "").strip().lower() in ("1", "true", "yes")
        self._gateway = os.environ.get("GOVMCP_GATEWAY", "").rstrip("/")
        self._gateway_key = os.environ.get("GOVMCP_GATEWAY_KEY", "")
        self._httpx = None
        try:
            import httpx; self._httpx = httpx
        except ImportError:
            logger.warning("httpx not installed")

    def available(self) -> bool:
        return not self._disabled and self._httpx is not None and bool(self._refresh_key())

    def _refresh_key(self) -> str:
        """惰性刷新 API Key（自愈机制）。

        LLMClient 是进程级单例，构造时可能早于 envboot 注入环境变量
        （如模块导入期/cordis 装配期被首次引用），导致 _api_key 永久为空、
        所有调用报 "no api key (provider not configured)"。每次调用前兜底
        重读 os.environ 与 ~/.eco/.env，一旦拿到有效 Key 即自愈。
        """
        if self._api_key:
            return self._api_key
        env: dict = {}
        try:
            # 兜底链：~/.eco/.env 之后并入仓库 .env（后者非空值优先），
            # 与 envboot 语义一致（真实环境 > 仓库 .env > ~/.eco/.env）
            from agent_core.envboot import _parse_env_file

            user_file = Path.home() / ".eco" / ".env"
            repo_file = Path(__file__).resolve().parent.parent / ".env"
            env = _parse_env_file(user_file)
            for k, v in _parse_env_file(repo_file).items():
                if v.strip():  # 仓库 .env 的空值不覆盖用户级非空值
                    env[k] = v
        except OSError:
            pass
        key = os.environ.get(self._provider["api_key_env"]) or env.get(
            self._provider["api_key_env"], ""
        )
        if key:
            self._api_key = key
            logger.info("[llm_client] api key 惰性刷新成功: %s", self._provider["api_key_env"])
        else:
            # 自诊断：下一次复发时这行日志直接定位缺的是哪一环
            logger.error(
                "[llm_client] api key 缺失诊断: provider=%s env_key=%s "
                "os_environ_has_key=%s eco_env_file_has_key=%s cwd=%s python=%s",
                self._provider_name, self._provider["api_key_env"],
                bool(os.environ.get(self._provider["api_key_env"])),
                bool(env.get(self._provider["api_key_env"])),
                os.getcwd(), sys.executable if hasattr(sys, "executable") else "?")
        return self._api_key

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
        _t0 = time.time()
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
                try:
                    record_llm_stat(self._provider_name, self._provider["default_model"],
                                    round((time.time() - _t0) * 1000, 1),
                                    (data.get("usage") or {}).get("prompt_tokens"),
                                    (data.get("usage") or {}).get("completion_tokens"),
                                    path="complete", ok=True)
                except Exception:
                    pass
                return text.strip()
            body = resp.text[:300]
            logger.warning(f"[complete] HTTP {resp.status_code}: {body}")
            kind = "quota" if self._is_quota_error(resp.status_code, body) else "http"
            self._last_error = {"kind": kind, "status": resp.status_code, "detail": body}
            try:
                record_llm_stat(self._provider_name, self._provider["default_model"],
                                round((time.time() - _t0) * 1000, 1), path="complete", ok=False)
            except Exception:
                pass
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
        返回是否切换成功（目标 provider 有可用密钥）。
        除历史 PROVIDERS 外，也接受注册表（agent_core.llm_providers）中的新 provider 名。"""
        prov = PROVIDERS.get(name)
        if prov is not None:
            key = os.environ.get(prov["api_key_env"]) or self._env.get(prov["api_key_env"], "")
            if not key:
                return False
            self._provider_name = name
            self._provider = prov
            self._api_key = key
            self._last_error = None
            logger.warning(f"[llm_client] switched to provider: {name}")
            return True
        spec = REGISTRY_PROVIDERS.get((name or "").strip().lower())
        if spec is None:
            return False
        if not self._apply_provider_spec(spec):
            return False
        logger.warning(f"[llm_client] switched to provider: {spec.name}")
        return True

    # ------------------------------------------------------------------
    # SPEC 模块 A：注册表集成
    # ------------------------------------------------------------------
    def _apply_provider_spec(self, spec) -> bool:
        """按注册表 ProviderSpec 重建 provider 配置与密钥；无 key 返回 False。"""
        base_url = spec.base_url
        model = spec.default_model
        if spec.name == "custom":
            base_url = (os.environ.get("ECO_CUSTOM_BASE_URL")
                        or self._env.get("ECO_CUSTOM_BASE_URL", "")).rstrip("/")
            model = (os.environ.get("ECO_CUSTOM_MODEL")
                     or self._env.get("ECO_CUSTOM_MODEL", "") or spec.default_model)
        key = os.environ.get(spec.env_key) or self._env.get(spec.env_key, "")
        if spec.name == "moonshot" and not key:
            # 历史兼容：KIMI_API_KEY 也可用于 moonshot provider
            key = os.environ.get("KIMI_API_KEY") or self._env.get("KIMI_API_KEY", "")
        if spec.name == "ollama" and not key:
            key = "ollama"  # 本地 Ollama 不校验 key，占位即可
        if not key or not base_url:
            return False
        self._provider_name = spec.name
        self._provider = {"base_url": base_url, "api_key_env": spec.env_key,
                          "default_model": model, "embedding_model": None}
        self._api_key = key
        self._last_error = None
        return True

    @classmethod
    def from_provider(cls, name: str) -> "LLMClient":
        """按注册表名构造 client（SPEC 模块 A）。
        找不到名字抛 KeyError（列出可用名）；有名字但没配 key 时返回的 client
        available() 为 False，由调用方决定降级或报错。"""
        from agent_core.llm_providers import get_provider
        spec = get_provider(name)
        client = cls()
        if not client._apply_provider_spec(spec):
            # 允许构造（如无 key 的 ollama 本地场景由上层兜底），但标记为无 key
            base_url = spec.base_url
            model = spec.default_model
            if spec.name == "custom":
                base_url = (os.environ.get("ECO_CUSTOM_BASE_URL")
                            or client._env.get("ECO_CUSTOM_BASE_URL", "")).rstrip("/")
                model = (os.environ.get("ECO_CUSTOM_MODEL")
                         or client._env.get("ECO_CUSTOM_MODEL", ""))
            client._provider_name = spec.name
            client._provider = {"base_url": base_url, "api_key_env": spec.env_key,
                                "default_model": model, "embedding_model": None}
            client._api_key = ""
        return client

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
                try:
                    usage = result.get("usage") or {}
                    record_llm_stat(self._provider_name, model,
                                    round((time.time() - start) * 1000, 1),
                                    usage.get("prompt_tokens"), usage.get("completion_tokens"),
                                    path=f"chat:{_kind}", ok=True)
                except Exception:
                    pass
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
                json={"model": model, "messages": messages,
                      "temperature": self._resolve_temperature(model, 0.7), "stream": True},
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

    def _call_chat_with_tools(self, model: str, messages: list, tools: list):
        """单次 chat_with_tools HTTP 调用。成功返回 (message_dict, None)，
        失败返回 (None, err) 并把细节写入 self._last_error。
        温度统一经 _resolve_temperature 收口（kimi-k2.x 强制 1）。"""
        self._last_error = None
        # 空密钥守卫：provider 未配置 Key 时直接短路返回，绝不构造
        # "Bearer " 空头（httpx 会抛 Illegal header value 炸掉调用链）。
        # 先惰性刷新（单例构造早于 envboot 时自愈），仍为空才短路。
        if not self._refresh_key():
            self._last_error = {"kind": "auth", "status": None,
                                "detail": "no api key (provider not configured)"}
            return None, "no api key (provider not configured)"
        body = {
            "model": model,
            "messages": messages,
            "temperature": self._resolve_temperature(model, 0.7),
            "stream": False,
        }
        # v4 推理档位（可选）：ECO_REASONING_EFFORT=high/max 控制思考深度与首字延迟
        _effort = os.environ.get("ECO_REASONING_EFFORT", "").strip()
        if _effort and model.startswith("deepseek-v4"):
            body["reasoning_effort"] = _effort
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        t0 = time.time()
        try:
            resp = self._httpx.post(
                f"{self._provider['base_url']}/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                json=body,
                timeout=60,
            )
            if resp.status_code != 200:
                detail = resp.text[:300] if getattr(resp, "text", None) else ""
                kind = "quota" if self._is_quota_error(resp.status_code, detail) else (
                    "auth" if resp.status_code in (401, 403) else "http")
                self._last_error = {"kind": kind, "status": resp.status_code, "detail": detail}
                self._record_usage(model, None, time.time() - t0, ok=False)
                return None, f"HTTP {resp.status_code}"
            data = resp.json()
            usage = data.get("usage")
            self._record_usage(model, usage, time.time() - t0, ok=True)
            msg = data.get("choices", [{}])[0].get("message", {})
            # 会话级 token 计量：usage 随消息带回（chat.py 循环累加后剥离，不下发模型）
            if isinstance(msg, dict):
                msg["_usage"] = usage
                # 推理模型（deepseek-reasoner/v4 系列）返回 reasoning_content ——
                # 采集进 _reasoning，chat.py 转为 think 事件推给前端（DSH Think 流）
                if msg.get("reasoning_content"):
                    msg["_reasoning"] = msg["reasoning_content"]
            return msg, None
        except Exception as e:
            self._last_error = {"kind": "network", "status": None, "detail": f"{type(e).__name__} {e}"}
            self._record_usage(model, None, time.time() - t0, ok=False)
            return None, str(e)

    def _call_chat_with_tools_stream(self, model: str, messages: list, tools: list,
                                     on_chunk=None, on_reasoning=None):
        """真实 SSE 流式 chat_with_tools 调用（stream=True）。

        - content delta 即时通过 on_chunk 回调给上层（真流式，非整块切片回放）
        - tool_calls delta 按 index 增量拼装（id/name 一次性到达，arguments 分片）
        - usage 在流末尾（或单独 usage chunk）记录
        - 返回 (message_dict, None)；失败返回 (None, err) 并写 self._last_error，
          429/配额类错误交由上层做 provider 流式降级重试。
        """
        self._last_error = None
        # 空密钥守卫（同 _call_chat_with_tools，先惰性刷新自愈）
        if not self._refresh_key():
            self._last_error = {"kind": "auth", "status": None,
                                "detail": "no api key (provider not configured)"}
            return None, "no api key (provider not configured)"
        body = {
            "model": model,
            "messages": messages,
            "temperature": self._resolve_temperature(model, 0.7),
            "stream": True,
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        t0 = time.time()
        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        tool_calls_acc: dict[int, dict] = {}
        usage = None
        try:
            with self._httpx.stream(
                "POST",
                f"{self._provider['base_url']}/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                json=body,
                timeout=120,
            ) as resp:
                if resp.status_code != 200:
                    try:
                        raw = resp.read()
                        detail = (raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw))[:300]
                    except Exception:
                        detail = ""
                    kind = "quota" if self._is_quota_error(resp.status_code, detail) else (
                        "auth" if resp.status_code in (401, 403) else "http")
                    self._last_error = {"kind": kind, "status": resp.status_code, "detail": detail}
                    self._record_usage(model, None, time.time() - t0, ok=False)
                    return None, f"HTTP {resp.status_code}"
                for line in resp.iter_lines():
                    if not line:
                        continue
                    line = line.decode("utf-8") if isinstance(line, bytes) else line
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    if data.get("usage"):
                        usage = data["usage"]
                    choices = data.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    chunk = delta.get("content")
                    if chunk:
                        content_parts.append(chunk)
                        if on_chunk:
                            on_chunk(chunk)
                    rchunk = delta.get("reasoning_content")
                    if rchunk:
                        reasoning_parts.append(rchunk)
                        if on_reasoning:
                            on_reasoning(rchunk)
                    for tc in delta.get("tool_calls") or []:
                        idx = tc.get("index", 0)
                        acc = tool_calls_acc.setdefault(
                            idx, {"id": "", "type": "function",
                                  "function": {"name": "", "arguments": ""}})
                        if tc.get("id"):
                            acc["id"] = tc["id"]
                        fn = tc.get("function") or {}
                        if fn.get("name"):
                            acc["function"]["name"] += fn["name"]
                        if fn.get("arguments"):
                            acc["function"]["arguments"] += fn["arguments"]
            message = {"role": "assistant", "content": "".join(content_parts) or None}
            if reasoning_parts:
                message["_reasoning"] = "".join(reasoning_parts)
            if tool_calls_acc:
                message["tool_calls"] = [tool_calls_acc[i] for i in sorted(tool_calls_acc)]
            self._record_usage(model, usage, time.time() - t0, ok=True)
            message["_usage"] = usage
            return message, None
        except Exception as e:
            self._last_error = {"kind": "network", "status": None, "detail": f"{type(e).__name__} {e}"}
            self._record_usage(model, None, time.time() - t0, ok=False)
            return None, str(e)

    @staticmethod
    def _is_recoverable_error(err: dict) -> bool:
        """401/402/403/429/5xx/网络错误均可尝试 provider 降级"""
        return err.get("kind") in ("quota", "auth", "http", "network")

    def _try_failover_provider(self) -> bool:
        """切换到备用 provider（deepseek <-> kimi，取有可用 Key 的一方）"""
        peer = "deepseek" if self._provider_name == "kimi" else "kimi"
        if self.switch_provider(peer):
            return True
        # 兜底：尝试任意有 key 的其他 provider
        return any(name != self._provider_name and self.switch_provider(name) for name in PROVIDERS)

    @staticmethod
    def _friendly_error(err: dict | None) -> str:
        if not err:
            return "未知错误"
        kind, status, detail = err.get("kind"), err.get("status"), (err.get("detail") or "")[:120]
        if kind == "auth":
            return f"API Key 无效或已过期（HTTP {status}）"
        if kind == "quota":
            return f"模型配额不足或被限流（HTTP {status}）"
        if kind == "http":
            return f"模型服务返回 HTTP {status}: {detail}"
        if kind == "network":
            return f"网络连接失败: {detail}"
        if kind == "unavailable":
            return "未配置 API Key（请运行 eco setup）"
        return f"{kind}: {detail}"

    def _record_usage(self, model: str, usage: dict | None, elapsed_s: float, ok: bool):
        """结构化统计：每次 LLM 调用记录 tokens+latency 到 ~/.eco/stats.jsonl"""
        self._last_usage = dict(usage or {})
        try:
            record_llm_stat(
                provider=self._provider_name, model=model,
                latency_ms=round(elapsed_s * 1000, 1),
                prompt_tokens=(usage or {}).get("prompt_tokens"),
                completion_tokens=(usage or {}).get("completion_tokens"),
                path="chat_with_tools", ok=ok)
        except Exception:
            pass

    def chat_with_tools(self, messages: list, tools: list, on_chunk=None, max_tool_rounds: int = 5,
                        tracer=None, stream: bool = False, spans=None) -> str:
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
            stream: True 时走真实 SSE 流式请求（_call_chat_with_tools_stream），
                    content delta 即时回调；429 等错误同样触发 provider 流式降级
            spans: 可选 agent_core.observability.SpanTree，记录 llm_call/tool_call
                   嵌套 span（耗时/tokens/parent_id），供 eco trace --tree 展示
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
            if tracer is not None and getattr(tracer, "enabled", False):
                tracer.round_start(_round_idx + 1)
            # 调用 LLM（温度统一走 _resolve_temperature 收口：kimi-k2.x 强制 temp=1）
            # stream=True 走真实 SSE 流式（content delta 即时回调，tool_calls 按 index 拼装）；
            # 失败时按 provider fallback 链降级重试（Kimi 401/429 → DeepSeek 等，流式同样降级）
            def _call(mdl, msgs):
                if stream:
                    return self._call_chat_with_tools_stream(mdl, msgs, tools, on_chunk=on_chunk)
                return self._call_chat_with_tools(mdl, msgs, tools)

            llm_span = spans.start(f"round{_round_idx + 1}", "llm_call", model=model,
                                   provider=self._provider_name) if spans is not None else None
            msg, err = _call(model, current_messages)
            if msg is None:
                if self._is_recoverable_error(self._last_error or {}) and self._try_failover_provider():
                    model = self._provider["default_model"]
                    logger.warning(f"[chat_with_tools] 主 provider 失败，已降级到 {self._provider_name} 重试")
                    if on_chunk:
                        on_chunk(f"\n  [提示] 主模型不可用（{self._friendly_error(self._last_error)}），"
                                 f"已自动切换到备用模型 {model} 重试...\n")
                    msg, err = _call(model, current_messages)
            if msg is None:
                if spans is not None and llm_span:
                    spans.end(llm_span, finish_reason="error",
                              error=self._friendly_error(self._last_error))
                friendly = (f"[API 错误] {self._friendly_error(self._last_error)}\n"
                            f"建议：检查 ~/.eco/.env 中的 API Key 是否有效（可运行 eco setup 重新配置），"
                            f"或切换 ECO_PROVIDER 到其他已配置 Key 的模型。")
                if on_chunk: on_chunk(friendly)
                return friendly

            # 检查是否有 tool_calls
            tool_calls = msg.get("tool_calls")
            # ── LLM 决策留痕：候选工具数/选中工具/原始 tool_calls 或 stop 原因/prompt 阶段 ──
            try:
                from agent_core.decisions import record_decision
                record_decision(
                    candidate_tools=len(tools or []),
                    selected_tools=[tc["function"]["name"] for tc in tool_calls] if tool_calls else [],
                    finish_reason="tool_calls" if tool_calls else "stop",
                    raw_tool_calls=tool_calls or [],
                    model=model, provider=self._provider_name, round_idx=_round_idx + 1)
            except Exception:
                pass  # 留痕失败不影响主流程
            if spans is not None and llm_span:
                u = self._last_usage or {}
                # 暂不结束 llm span：tool_call span 需嵌套在其下；
                # 在工具执行完 / 生成最终回答两个分支分别 end
                for k, v in (("finish_reason", "tool_calls" if tool_calls else "stop"),
                             ("prompt_tokens", u.get("prompt_tokens")),
                             ("completion_tokens", u.get("completion_tokens"))):
                    span_obj = next((s for s in spans.spans if s["span_id"] == llm_span), None)
                    if span_obj is not None:
                        span_obj["attrs"][k] = v
            if tool_calls:
                if tracer is not None and getattr(tracer, "enabled", False):
                    tracer.thought(msg.get("content") or "")
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

                    _trace_it = tracer is not None and getattr(tracer, "enabled", False)
                    if _trace_it:
                        tracer.tool_call(tool_name, tool_args)
                    tool_span = spans.start(tool_name, "tool_call",
                                            args=tool_args) if spans is not None else None
                    _t0 = __import__("time").time()
                    tool_result = asyncio.run(execute_tool(tool_name, tool_args))
                    _tel = __import__("time").time() - _t0
                    if tool_span is not None:
                        spans.end(tool_span, result=str(tool_result)[:200])
                    if _trace_it:
                        tracer.tool_result(tool_name, tool_result, _tel)

                    current_messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": tool_result
                    })

                if spans is not None and llm_span:
                    spans.end(llm_span)
                continue  # 继续循环

            # 没有 tool_calls，有文本回答 → 输出
            content = msg.get("content") or ""
            if not content:
                content = str(msg)

            if tracer is not None and getattr(tracer, "enabled", False):
                tracer.finish("结束（生成最终回答）")

            if spans is not None and llm_span:
                spans.end(llm_span)

            if on_chunk and not stream:
                # 非流式路径：模拟流式输出（逐段展示）；真流式时内容已随 SSE delta 即时回调
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
