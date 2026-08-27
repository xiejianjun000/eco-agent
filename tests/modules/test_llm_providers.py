"""模块 A：provider 注册表 + llm_client 集成 + CLI model 子命令测试（全部 mock，禁止真实外呼）"""
import pytest

from agent_core.llm_providers import (
    PROVIDERS, ProviderSpec, available_providers, get_provider,
    list_providers, resolve_provider,
)

EXPECTED = {
    "moonshot", "deepseek", "zhipu", "qwen", "wenxin", "doubao", "hunyuan",
    "spark", "minimax", "stepfun", "baichuan", "sensenova", "ollama",
    "openrouter", "custom",
}
CAPS_ALL = {"tools", "stream", "json", "vision"}


class TestRegistry:
    def test_all_15_providers_registered(self):
        assert set(PROVIDERS) == EXPECTED
        assert len(list_providers()) == 15

    def test_provider_spec_fields(self):
        for spec in list_providers():
            assert isinstance(spec, ProviderSpec)
            assert spec.name and spec.display
            assert spec.env_key
            assert spec.caps <= CAPS_ALL
            assert isinstance(spec.models, list)
            if spec.name not in ("custom",):
                assert spec.base_url.startswith("http"), spec.name
                assert spec.default_model, spec.name

    def test_key_endpoints(self):
        assert get_provider("moonshot").base_url == "https://api.moonshot.cn/v1"
        assert get_provider("zhipu").base_url == "https://open.bigmodel.cn/api/paas/v4"
        assert "compatible-mode" in get_provider("qwen").base_url
        assert get_provider("ollama").base_url == "http://localhost:11434/v1"
        assert get_provider("moonshot").default_model == "kimi-k2.5"
        assert get_provider("zhipu").default_model == "glm-4.6"

    def test_get_provider_unknown_raises_with_available_names(self):
        with pytest.raises(KeyError) as ei:
            get_provider("nonexistent")
        msg = ei.value.args[0]
        assert "moonshot" in msg and "deepseek" in msg

    def test_get_provider_case_insensitive(self):
        assert get_provider(" MoonShot ").name == "moonshot"


class TestResolve:
    def test_explicit_name_wins(self):
        assert resolve_provider("zhipu", {}).name == "zhipu"

    def test_env_var_fallback(self):
        assert resolve_provider(None, {"ECO_LLM_PROVIDER": "qwen"}).name == "qwen"

    def test_kimi_then_moonshot_then_deepseek_order(self):
        assert resolve_provider(None, {"KIMI_API_KEY": "k"}).name == "moonshot"
        assert resolve_provider(None, {"MOONSHOT_API_KEY": "k"}).name == "moonshot"
        assert resolve_provider(None, {"DEEPSEEK_API_KEY": "k"}).name == "deepseek"
        assert resolve_provider(
            None, {"KIMI_API_KEY": "k", "DEEPSEEK_API_KEY": "k"}).name == "moonshot"

    def test_first_available_fallback(self):
        spec = resolve_provider(None, {"HUNYUAN_API_KEY": "k"})
        assert spec.name == "hunyuan"

    def test_no_key_defaults_deepseek(self):
        assert resolve_provider(None, {}).name == "deepseek"

    def test_invalid_env_name_falls_through(self):
        assert resolve_provider(None, {"ECO_LLM_PROVIDER": "bogus",
                                       "DEEPSEEK_API_KEY": "k"}).name == "deepseek"


class TestAvailable:
    def test_available_filters_by_env_key(self):
        env = {"DEEPSEEK_API_KEY": "k", "ZHIPU_API_KEY": "k"}
        names = {s.name for s in available_providers(env)}
        assert names == {"deepseek", "zhipu"}

    def test_custom_requires_base_url(self):
        assert "custom" not in {s.name for s in available_providers({})}
        env = {"ECO_CUSTOM_BASE_URL": "http://x/v1"}
        assert "custom" in {s.name for s in available_providers(env)}

    def test_empty_env_none_available(self):
        assert available_providers({}) == []


class TestLLMClientIntegration:
    def test_legacy_providers_dict_backward_compat(self):
        from agent_core.llm_client import PROVIDERS as LEGACY
        assert LEGACY["deepseek"]["base_url"] == "https://api.deepseek.com/v1"
        assert LEGACY["deepseek"]["default_model"] == "deepseek-v4-pro"
        assert LEGACY["kimi"]["base_url"] == "https://api.moonshot.cn/v1"
        assert LEGACY["kimi"]["api_key_env"] == "KIMI_API_KEY"
        assert LEGACY["kimi"]["default_model"] == "kimi-k2.5"
        assert LEGACY["kimi"]["embedding_model"] == "moonshot-v1-embedding"
        assert LEGACY["qwen"]["api_key_env"] == "DASHSCOPE_API_KEY"
        assert LEGACY["doubao"]["api_key_env"] == "DOUBAO_API_KEY"
        assert set(LEGACY) == {"deepseek", "openai", "anthropic", "kimi", "qwen", "doubao"}

    def test_from_provider(self, monkeypatch):
        from agent_core.llm_client import LLMClient
        monkeypatch.setenv("ZHIPU_API_KEY", "sk-test-zhipu")
        c = LLMClient.from_provider("zhipu")
        assert c._provider_name == "zhipu"
        assert c._provider["base_url"] == "https://open.bigmodel.cn/api/paas/v4"
        assert c._provider["default_model"] == "glm-4.6"
        assert c._api_key == "sk-test-zhipu"

    def test_from_provider_unknown_raises(self):
        from agent_core.llm_client import LLMClient
        with pytest.raises(KeyError):
            LLMClient.from_provider("nope")

    def test_from_provider_moonshot_kimi_key_compat(self, monkeypatch):
        from agent_core.llm_client import LLMClient
        monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
        monkeypatch.setenv("KIMI_API_KEY", "sk-kimi")
        c = LLMClient.from_provider("moonshot")
        assert c._api_key == "sk-kimi"

    def test_from_provider_custom(self, monkeypatch):
        from agent_core.llm_client import LLMClient
        monkeypatch.setenv("ECO_CUSTOM_BASE_URL", "http://10.0.0.1:9000/v1/")
        monkeypatch.setenv("ECO_CUSTOM_API_KEY", "sk-c")
        monkeypatch.setenv("ECO_CUSTOM_MODEL", "my-model")
        c = LLMClient.from_provider("custom")
        assert c._provider["base_url"] == "http://10.0.0.1:9000/v1"
        assert c._provider["default_model"] == "my-model"

    def test_from_provider_no_key_unavailable(self, monkeypatch):
        from agent_core.llm_client import LLMClient
        monkeypatch.delenv("HUNYUAN_API_KEY", raising=False)
        c = LLMClient.from_provider("hunyuan")
        assert c._api_key == ""
        assert not c.available()

    def test_switch_provider_accepts_registry_names(self, monkeypatch):
        from agent_core.llm_client import LLMClient
        monkeypatch.setenv("SPARK_API_KEY", "sk-spark")
        c = LLMClient()
        assert c.switch_provider("spark")
        assert c._provider_name == "spark"
        assert c._provider["default_model"] == "generalv3.5"
        assert not c.switch_provider("no-such-provider")

    def test_resolve_temperature_kept(self):
        from agent_core.llm_client import LLMClient
        assert LLMClient._resolve_temperature("kimi-k2.5", 0.7) == 1
        assert LLMClient._resolve_temperature("Kimi-K2-0905", 0.3) == 1
        assert LLMClient._resolve_temperature("deepseek-chat", 0.7) == 0.7


# ---------------------------------------------------------------------------
# CLI：eco config model list / use / test（全部 mock）
# ---------------------------------------------------------------------------
def _args(**kw):
    import argparse
    defaults = dict(action="model", key=None, value=None)
    defaults.update(kw)
    return argparse.Namespace(**defaults)


class TestCLIModel:
    def test_model_list_table(self, capsys, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-x")
        from eco.commands import cmd_config
        rc = cmd_config.run(_args(key="list"))
        out = capsys.readouterr().out
        assert rc == 0
        for name in EXPECTED:
            assert name in out
        # deepseek 有 key 标 ✅；无 key 的行标 ❌
        line = [l for l in out.splitlines() if l.startswith("deepseek")][0]
        assert "✅" in line
        line = [l for l in out.splitlines() if l.startswith("hunyuan")][0]
        assert "❌" in line

    def test_model_use_writes_config(self, tmp_path, monkeypatch, capsys):
        from eco.commands import cmd_config
        monkeypatch.setattr(cmd_config, "ENV_FILE", tmp_path / ".env")
        rc = cmd_config.run(_args(key="use", value="zhipu"))
        assert rc == 0
        assert "ECO_LLM_PROVIDER=zhipu" in (tmp_path / ".env").read_text()
        assert "zhipu" in capsys.readouterr().out

    def test_model_use_unknown_name(self, tmp_path, monkeypatch, capsys):
        from eco.commands import cmd_config
        monkeypatch.setattr(cmd_config, "ENV_FILE", tmp_path / ".env")
        rc = cmd_config.run(_args(key="use", value="bogus"))
        assert rc == 2
        assert "可用" in capsys.readouterr().out

    def test_model_test_success(self, tmp_path, monkeypatch, capsys):
        from eco.commands import cmd_config
        from agent_core.llm_client import LLMClient
        monkeypatch.setattr(cmd_config, "ENV_FILE", tmp_path / ".env")
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        calls = {}

        def fake_complete(self, prompt, system="", max_tokens=512, timeout=90.0):
            calls["prompt"] = prompt
            calls["url"] = self._provider["base_url"]
            return "pong"
        monkeypatch.setattr(LLMClient, "complete", fake_complete)
        rc = cmd_config.run(_args(key="test", value="deepseek"))
        out = capsys.readouterr().out
        assert rc == 0
        assert calls["prompt"] == "ping"
        assert calls["url"] == "https://api.deepseek.com/v1"
        assert "✅" in out and "pong" in out

    def test_model_test_no_key_clear_error(self, tmp_path, monkeypatch, capsys):
        from eco.commands import cmd_config
        monkeypatch.setattr(cmd_config, "ENV_FILE", tmp_path / ".env")
        monkeypatch.delenv("HUNYUAN_API_KEY", raising=False)
        rc = cmd_config.run(_args(key="test", value="hunyuan"))
        out = capsys.readouterr().out
        assert rc == 1
        assert "HUNYUAN_API_KEY" in out

    def test_model_test_failure_shows_friendly_error(self, tmp_path, monkeypatch, capsys):
        from eco.commands import cmd_config
        from agent_core.llm_client import LLMClient
        monkeypatch.setattr(cmd_config, "ENV_FILE", tmp_path / ".env")
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")

        def fake_complete(self, prompt, system="", max_tokens=512, timeout=90.0):
            self._last_error = {"kind": "auth", "status": 401, "detail": "bad key"}
            return ""
        monkeypatch.setattr(LLMClient, "complete", fake_complete)
        rc = cmd_config.run(_args(key="test", value="deepseek"))
        out = capsys.readouterr().out
        assert rc == 1
        assert "❌" in out and "401" in out

    def test_model_test_default_resolve(self, tmp_path, monkeypatch, capsys):
        """不带 name 时按注册表回退链解析（KIMI_API_KEY → moonshot）"""
        from eco.commands import cmd_config
        from agent_core.llm_client import LLMClient
        monkeypatch.setattr(cmd_config, "ENV_FILE", tmp_path / ".env")
        for k in ("MOONSHOT_API_KEY", "DEEPSEEK_API_KEY", "ECO_LLM_PROVIDER", "ECO_PROVIDER"):
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setenv("KIMI_API_KEY", "sk-kimi")
        seen = {}
        monkeypatch.setattr(LLMClient, "complete",
                            lambda self, prompt, **kw: seen.setdefault("url", self._provider["base_url"]) or "ok")
        rc = cmd_config.run(_args(key="test"))
        assert rc == 0
        assert seen["url"] == "https://api.moonshot.cn/v1"

    def test_config_legacy_actions(self, tmp_path, monkeypatch, capsys):
        from eco.commands import cmd_config
        monkeypatch.setattr(cmd_config, "ENV_FILE", tmp_path / ".env")
        assert cmd_config.run(_args(action="init")) == 0
        assert cmd_config.run(_args(action="set", key="FOO", value="bar")) == 0
        capsys.readouterr()
        assert cmd_config.run(_args(action="get", key="FOO")) == 0
        assert capsys.readouterr().out.strip() == "bar"
