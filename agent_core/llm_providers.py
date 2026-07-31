#!/usr/bin/env python3
"""llm_providers.py - 国产/海外大模型 provider 注册表（模块 A）

对标 Hermes 200+ 模型接入：统一 OpenAI 兼容端点注册表，
供 llm_client / CLI（eco config model list|use|test）使用。

接口契约（SPEC 模块 A）：
  ProviderSpec / PROVIDERS / get_provider / list_providers /
  resolve_provider / available_providers

铁律：本文件不含任何真实 API key，一律走环境变量占位符。
"""
import os
from dataclasses import dataclass, field

# 能力标签全集
CAPS_ALL = {"tools", "stream", "json", "vision"}


@dataclass
class ProviderSpec:
    name: str            # 唯一标识，如 "moonshot"
    display: str         # 中文显示名，如 "月之暗面 Kimi"
    base_url: str        # OpenAI 兼容端点
    env_key: str         # API key 环境变量名，如 "MOONSHOT_API_KEY"
    default_model: str
    models: list         # 推荐模型清单 list[str]
    caps: set            # {"tools","stream","json","vision"} 子集 set[str]
    doc: str = ""        # 申请 key 的入口 URL

    def has_key(self, env: dict | None = None) -> bool:
        """环境里（os.environ 或 ~/.eco/.env 快照）是否有该 provider 的 key"""
        e = os.environ if env is None else env
        return bool(e.get(self.env_key))


# ---------------------------------------------------------------------------
# 内置 provider 注册表（base_url 以各官方文档为准；不确定的取社区公认值并注释）
# ---------------------------------------------------------------------------
PROVIDERS: dict[str, ProviderSpec] = {}


def _register(spec: ProviderSpec) -> None:
    PROVIDERS[spec.name] = spec


_register(ProviderSpec(
    name="moonshot", display="月之暗面 Kimi",
    base_url="https://api.moonshot.cn/v1",
    env_key="MOONSHOT_API_KEY",
    default_model="kimi-k2.5",
    models=["kimi-k2.5", "kimi-k2-0905-preview", "moonshot-v1-128k"],
    caps={"tools", "stream", "json"},
    doc="https://platform.moonshot.cn/console/api-keys",
))

_register(ProviderSpec(
    name="deepseek", display="深度求索 DeepSeek",
    base_url="https://api.deepseek.com/v1",
    env_key="DEEPSEEK_API_KEY",
    default_model="deepseek-chat",
    models=["deepseek-chat", "deepseek-reasoner"],
    caps={"tools", "stream", "json"},
    doc="https://platform.deepseek.com/api_keys",
))

_register(ProviderSpec(
    name="zhipu", display="智谱 GLM",
    base_url="https://open.bigmodel.cn/api/paas/v4",  # 官方 OpenAI 兼容端点
    env_key="ZHIPU_API_KEY",
    default_model="glm-4.6",
    models=["glm-4.6", "glm-4.5", "glm-4.5-air"],
    caps={"tools", "stream", "json", "vision"},
    doc="https://open.bigmodel.cn/usercenter/apikeys",
))

_register(ProviderSpec(
    name="qwen", display="阿里通义千问",
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",  # DashScope 兼容模式
    env_key="DASHSCOPE_API_KEY",
    default_model="qwen-max",
    models=["qwen-max", "qwen-plus", "qwen-turbo", "qwen3-235b-a22b"],
    caps={"tools", "stream", "json", "vision"},
    doc="https://bailian.console.aliyun.com/#/api-key",
))

_register(ProviderSpec(
    name="wenxin", display="百度文心一言（千帆）",
    base_url="https://qianfan.baidubce.com/v2",  # 千帆 v2 OpenAI 兼容端点
    env_key="QIANFAN_API_KEY",
    default_model="ernie-4.5-turbo-128k",
    models=["ernie-4.5-turbo-128k", "ernie-x1-turbo-32k", "ernie-4.0-8k"],
    caps={"tools", "stream", "json"},
    doc="https://console.bce.baidu.com/qianfan/ais/console/apiKey",
))

_register(ProviderSpec(
    name="doubao", display="字节豆包（火山方舟）",
    base_url="https://ark.cn-beijing.volces.com/api/v3",
    env_key="ARK_API_KEY",
    default_model="doubao-pro-32k",  # 方舟现多用 endpoint id（ep-xxx），此处保留模型名占位
    models=["doubao-pro-32k", "doubao-1.5-pro-32k", "doubao-1.5-lite-32k"],
    caps={"tools", "stream", "json", "vision"},
    doc="https://console.volcengine.com/ark/region:ark+cn-beijing/apiKey",
))

_register(ProviderSpec(
    name="hunyuan", display="腾讯混元",
    base_url="https://api.hunyuan.cloud.tencent.com/v1",  # 官方 OpenAI 兼容端点
    env_key="HUNYUAN_API_KEY",
    default_model="hunyuan-turbo",
    models=["hunyuan-turbo", "hunyuan-pro", "hunyuan-standard"],
    caps={"tools", "stream", "json"},
    doc="https://console.cloud.tencent.com/hunyuan/api-key",
))

_register(ProviderSpec(
    name="spark", display="讯飞星火",
    base_url="https://spark-api-open.xf-yun.com/v1",  # 官方 OpenAI 兼容端点
    env_key="SPARK_API_KEY",
    default_model="generalv3.5",
    models=["generalv3.5", "generalv3", "spark-max", "4.0Ultra"],
    caps={"tools", "stream", "json"},
    doc="https://console.xfyun.cn/services/bm3",
))

_register(ProviderSpec(
    name="minimax", display="MiniMax",
    base_url="https://api.minimaxi.com/v1",  # 官方 OpenAI 兼容端点
    env_key="MINIMAX_API_KEY",
    default_model="MiniMax-M1",
    models=["MiniMax-M1", "abab6.5s-chat", "MiniMax-Text-01"],
    caps={"tools", "stream", "json"},
    doc="https://platform.minimaxi.com/user-center/basic-information/interface-key",
))

_register(ProviderSpec(
    name="stepfun", display="阶跃星辰 Step",
    base_url="https://api.stepfun.com/v1",
    env_key="STEPFUN_API_KEY",
    default_model="step-2-16k",
    models=["step-2-16k", "step-1-8k", "step-1v-8k"],
    caps={"tools", "stream", "json", "vision"},
    doc="https://platform.stepfun.com/account/api-keys",
))

_register(ProviderSpec(
    name="baichuan", display="百川智能",
    base_url="https://api.baichuan-ai.com/v1",  # 官方 OpenAI 兼容端点
    env_key="BAICHUAN_API_KEY",
    default_model="Baichuan4",
    models=["Baichuan4", "Baichuan3-Turbo", "Baichuan2-Turbo"],
    caps={"tools", "stream", "json"},
    doc="https://platform.baichuan-ai.com/console/apikey",
))

_register(ProviderSpec(
    name="sensenova", display="商汤日日新 SenseNova",
    base_url="https://api.sensenova.cn/v1",  # 公认 OpenAI 兼容端点（官方文档以控制台为准）
    env_key="SENSENOVA_API_KEY",
    default_model="SenseChat-5",
    models=["SenseChat-5", "SenseChat-32K", "SenseChat-Turbo"],
    caps={"tools", "stream", "json"},
    doc="https://console.sensenova.cn/",
))

_register(ProviderSpec(
    name="ollama", display="Ollama（本地）",
    base_url="http://localhost:11434/v1",
    env_key="OLLAMA_API_KEY",  # 本地一般无需 key；占位即可
    default_model="qwen2.5:7b",
    models=["qwen2.5:7b", "llama3.1:8b", "deepseek-r1:7b"],
    caps={"tools", "stream", "json"},
    doc="https://ollama.com/",
))

_register(ProviderSpec(
    name="openrouter", display="OpenRouter（聚合）",
    base_url="https://openrouter.ai/api/v1",
    env_key="OPENROUTER_API_KEY",
    default_model="anthropic/claude-sonnet-4",
    models=["anthropic/claude-sonnet-4", "openai/gpt-4o", "deepseek/deepseek-chat"],
    caps={"tools", "stream", "json", "vision"},
    doc="https://openrouter.ai/keys",
))

_register(ProviderSpec(
    name="custom", display="自定义（ECO_CUSTOM_BASE_URL）",
    base_url="",  # 运行时从 ECO_CUSTOM_BASE_URL 读取
    env_key="ECO_CUSTOM_API_KEY",
    default_model="",  # 运行时从 ECO_CUSTOM_MODEL 读取
    models=[],
    caps={"tools", "stream", "json"},
    doc="",
))


def get_provider(name: str) -> ProviderSpec:
    """按名字取 provider；找不到抛 KeyError 并列出可用名"""
    key = (name or "").strip().lower()
    spec = PROVIDERS.get(key)
    if spec is None:
        raise KeyError(
            f"未知 provider: {name!r}；可用: {', '.join(sorted(PROVIDERS))}"
        )
    return spec


def list_providers() -> list[ProviderSpec]:
    """全部注册 provider（按注册顺序）"""
    return list(PROVIDERS.values())


def available_providers(env: dict | None = None) -> list[ProviderSpec]:
    """env 里有 key 的 provider（custom 要求同时配了 base_url）"""
    e = os.environ if env is None else env
    out = []
    for spec in PROVIDERS.values():
        if spec.name == "custom":
            if e.get("ECO_CUSTOM_BASE_URL"):
                out.append(spec)
            continue
        if e.get(spec.env_key):
            out.append(spec)
    return out


def resolve_provider(name_or_env: str | None, env: dict | None = None) -> ProviderSpec:
    """解析当前应使用的 provider。

    回退顺序（SPEC 契约）：
      显式 name → ECO_LLM_PROVIDER → KIMI（KIMI_API_KEY）→ MOONSHOT（MOONSHOT_API_KEY）
      → DEEPSEEK → 第一个有 key 的 provider。
    """
    e = os.environ if env is None else env
    if name_or_env:
        return get_provider(name_or_env)
    forced = e.get("ECO_LLM_PROVIDER") or e.get("ECO_PROVIDER")
    if forced:
        try:
            return get_provider(forced)
        except KeyError:
            pass  # 非法名字继续回退而不是直接炸（CLI 有独立报错路径）
    # KIMI_API_KEY 与 MOONSHOT_API_KEY 都映射到 moonshot（历史兼容：kimi 单独 env）
    if e.get("KIMI_API_KEY") or e.get("MOONSHOT_API_KEY"):
        return PROVIDERS["moonshot"]
    if e.get("DEEPSEEK_API_KEY"):
        return PROVIDERS["deepseek"]
    avail = available_providers(e)
    if avail:
        return avail[0]
    return PROVIDERS["deepseek"]  # 无 key 时的兜底默认
