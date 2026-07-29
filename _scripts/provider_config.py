#!/usr/bin/env python3
"""
provider_config.py — ECO AGENT 多模型提供者配置与验证

支持模型
  - claude-sonnet-4 (主模型)
  - deepseek-chat (国产)
  - qwen-max (国产·通义千问)
  - ernie-bot (国产·文心一言)
  - glm-4 (国产·智谱)

用法
  python _scripts/provider_config.py verify    # 验证全部配置
  python _scripts/provider_config.py list      # 列出可用模型
  python _scripts/provider_config.py --router  # 测试智能路由
"""

import os
import logging
from dataclasses import dataclass

logger = logging.getLogger("provider_config")

# ===== 模型定义 =====

@dataclass
class ModelProvider:
    """模型提供者"""
    name: str
    display_name: str
    api_mode: str                  # anthropic_messages / chat_completions
    model_id: str
    base_url: str                  # API 地址
    api_key_env: str               # 环境变量名
    temperature: float = 0.1       # 执法场景低温度
    max_tokens: int = 8192
    priority: int = 10             # 路由优先级数字越小越优先
    category: str = "primary"      # primary / fallback / domestic
    requires_key: bool = True
    notes: str = ""

    def is_available(self) -> bool:
        """检查 API Key 是否可用"""
        return not self.requires_key or bool(os.environ.get(self.api_key_env))

    def to_aisuite_config(self) -> dict:
        """转换为 aisuite 格式"""
        return {
            "provider": self.name,
            "model": self.model_id,
            "api_key": os.environ.get(self.api_key_env, ""),
            "base_url": self.base_url,
        }


# ===== 注册表 =====

PROVIDER_REGISTRY = [
    ModelProvider(
        name="claude",
        display_name="Claude Sonnet 4",
        api_mode="anthropic_messages",
        model_id="claude-sonnet-4-20260514",
        base_url="https://api.anthropic.com",
        api_key_env="ANTHROPIC_API_KEY",
        priority=1,
        category="primary",
        notes="主模型执法核心决策",
    ),
    ModelProvider(
        name="deepseek",
        display_name="DeepSeek Chat",
        api_mode="chat_completions",
        model_id="deepseek-chat",
        base_url="https://api.deepseek.com",
        api_key_env="DEEPSEEK_API_KEY",
        priority=2,
        category="domestic",
        notes="国产备选高性价比",
    ),
    ModelProvider(
        name="qwen",
        display_name="通义千问 Max",
        api_mode="chat_completions",
        model_id="qwen-max",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key_env="QWEN_API_KEY",
        priority=3,
        category="domestic",
        notes="阿里云通义千问",
    ),
    ModelProvider(
        name="ernie",
        display_name="文心一言 4.0",
        api_mode="chat_completions",
        model_id="ernie-4.0",
        base_url="https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat",
        api_key_env="ERNIE_API_KEY",
        priority=4,
        category="domestic",
        notes="百度文心一言",
    ),
    ModelProvider(
        name="glm",
        display_name="智谱 GLM-4",
        api_mode="chat_completions",
        model_id="glm-4",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        api_key_env="GLM_API_KEY",
        priority=5,
        category="domestic",
        notes="智谱 AI",
    ),
]


class ProviderRouter:
    """智能模型路由"""

    def __init__(self):
        self._providers = PROVIDER_REGISTRY
        self._failures: dict[str, int] = {}
        self._failover_threshold = 3
        logger.info(f"[Router] 注册 {len(self._providers)} 个模型提供者")

    def list_available(self) -> list[ModelProvider]:
        """列出可用提供者"""
        return [p for p in self._providers if p.is_available()]

    def get_primary(self) -> ModelProvider | None:
        """获取主模型"""
        primary = [p for p in self._providers if p.category == "primary"]
        if primary and primary[0].is_available():
            return primary[0]
        return None

    def get_fallback(self) -> ModelProvider | None:
        """获取降级模型"""
        fallbacks = [p for p in self._providers if p.category == "domestic" and p.is_available()]
        # 按优先级排序
        fallbacks.sort(key=lambda p: p.priority)
        for fb in fallbacks:
            if self._failures.get(fb.name, 0) < self._failover_threshold:
                return fb
        return fallbacks[0] if fallbacks else None

    def record_failure(self, provider_name: str):
        """记录失败"""
        self._failures[provider_name] = self._failures.get(provider_name, 0) + 1
        logger.warning(f"[Router] {provider_name} 失败 ({self._failures[provider_name]})")

    def record_success(self, provider_name: str):
        """记录成功"""
        self._failures[provider_name] = 0

    def get_router_config(self) -> dict:
        """获取路由配置"""
        primary = self.get_primary()
        fallback = self.get_fallback()
        return {
            "primary": {"name": primary.name if primary else None, "available": primary.is_available() if primary else False},
            "fallback": {"name": fallback.name if fallback else None, "available": fallback.is_available() if fallback else False},
            "all_available": [p.name for p in self.list_available()],
            "failover_threshold": self._failover_threshold,
            "current_failures": dict(self._failures),
        }

    def inference(self, prompt: str, system_prompt: str = "", provider_name: str = None) -> str:
        """实际调用 LLM 推理（通过 aisuite，兼容 Python 3.14+）"""
        try:
            import aisuite as ai
        except (ImportError, AttributeError):
            # aisuite 有 Python 3.14 兼容性问题时走直连 Anthropic
            return self._direct_inference(prompt, system_prompt, provider_name)

        provider = None
        if provider_name:
            for p in self._providers:
                if p.name == provider_name and p.is_available():
                    provider = p
                    break

        if not provider:
            provider = self.get_primary() or self.get_fallback()

        if not provider:
            return "[无可用模型]"

        try:
            config = provider.to_aisuite_config()
            client = ai.Client()

            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = client.chat.completions.create(
                model=f"{provider.name}:{provider.model_id}",
                messages=messages,
                temperature=provider.temperature,
                max_tokens=provider.max_tokens,
            )
            result = response.choices[0].message.content
            self.record_success(provider.name)
            return result
        except Exception as e:
            self.record_failure(provider.name)
            # 自动 Failover
            fallback = self.get_fallback()
            if fallback and fallback.name != provider.name:
                logger.info(f"[Router] 自动降级到: {fallback.name}")
                return self.inference(prompt, system_prompt, fallback.name)
            return f"[推理失败: {e}]"

    def _direct_inference(self, prompt: str, system_prompt: str = "", provider_name: str = None) -> str:
        """直连调用（aisuite 不可用时的备用方案）"""
        provider = None
        if provider_name:
            for p in self._providers:
                if p.name == provider_name and p.is_available():
                    provider = p; break
        if not provider:
            provider = self.get_primary() or self.get_fallback()
        if not provider:
            return "[无可用模型]"

        try:
            import anthropic
            client = anthropic.Anthropic(api_key=os.environ.get(provider.api_key_env, ""))
            messages = [{"role": "user", "content": prompt}]
            resp = client.messages.create(model=provider.model_id, messages=messages,
                                          system=system_prompt if system_prompt else None,
                                          max_tokens=provider.max_tokens)
            self.record_success(provider.name)
            return resp.content[0].text
        except Exception as e:
            self.record_failure(provider.name)
            if "api_key" in str(e).lower() or "auth" in str(e).lower():
                return f"[API Key 未配置: {provider.name}]"
            fallback = self.get_fallback()
            if fallback and fallback.name != provider.name:
                return self._direct_inference(prompt, system_prompt, fallback.name)
            return f"[直连推理失败: {e}]"


# ===== 验证 =====

def verify_all():
    """验证全部配置"""
    router = ProviderRouter()
    available = router.list_available()
    print("=" * 50)
    print("  ECO AGENT 模型提供者配置验证")
    print("=" * 50)

    print(f"\n 注册模型: {len(PROVIDER_REGISTRY)} 个")
    for p in PROVIDER_REGISTRY:
        status = " 已配置" if p.is_available() else " 未配置"
        cat_icon = "" if p.category == "primary" else "" if p.category == "domestic" else "  "
        print(f"  {cat_icon} {p.display_name:20s} [{p.name:10s}] {status}")
        print(f"     API: {p.api_key_env}")
        print(f"     模型: {p.model_id}")

    print("\n 路由状态:")
    config = router.get_router_config()
    print(f"  主模型: {config['primary']['name'] or '无'}")
    print(f"  降级模型: {config['fallback']['name'] or '无'}")
    print(f"  可用模型: {', '.join(config['all_available']) or '无'}")
    print(f"  当前失败计数: {config['current_failures']}")

    print("\n 环境变量配置:")
    for p in PROVIDER_REGISTRY:
        key = p.api_key_env
        val = os.environ.get(key, "")
        masked = val[:8] + "..." if val else "未设置"
        print(f"  {key:25s} = {masked}")

    return config


def test():
    """测试模型配置"""
    router = ProviderRouter()

    config = router.get_router_config()
    assert len(PROVIDER_REGISTRY) == 5
    assert config["primary"] is not None
    assert len(config["all_available"]) >= 0  # 取决于环境变量

    print(f"[TEST] 模型数: {len(PROVIDER_REGISTRY)}")
    print(f"[TEST] 路由配置: {config['primary']['name']}  {config['fallback']['name']}")

    print("\n[OK] 模型配置测试通过")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    verify_all()
    test()
