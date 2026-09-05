#!/usr/bin/env python3
"""keystore.py 测试——三后端 CRUD / 0600 权限 / PBKDF2 派生 / vault mock / llm_providers 集成回退"""

import io
import json
import os
import stat
import sys
import urllib.error
import urllib.request

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from agent_core import keystore
from agent_core import llm_providers as lp
from agent_core.keystore import (
    EnvBackend,
    FileVaultBackend,
    VaultClientBackend,
    get_keystore,
)


# ---------------------------------------------------------------------------
# EnvBackend
# ---------------------------------------------------------------------------
class TestEnvBackend:
    def test_crud(self):
        env = {}
        b = EnvBackend(env)
        assert b.get("FOO_API_KEY") is None
        b.set("FOO_API_KEY", "v1")
        assert b.get("FOO_API_KEY") == "v1"
        assert b.list_keys() == ["FOO_API_KEY"]
        b.delete("FOO_API_KEY")
        assert b.get("FOO_API_KEY") is None
        assert b.list_keys() == []

    def test_default_uses_os_environ(self, monkeypatch):
        monkeypatch.setenv("SOME_TEST_TOKEN", "tok-1")
        assert EnvBackend().get("SOME_TEST_TOKEN") == "tok-1"

    def test_list_keys_filters_suffixes(self):
        env = {"A_KEY": "x", "B_TOKEN": "y", "C_SECRET": "z", "D_PLAIN": "w", "E_KEY": ""}
        assert EnvBackend(env).list_keys() == ["A_KEY", "B_TOKEN", "C_SECRET"]


# ---------------------------------------------------------------------------
# FileVaultBackend
# ---------------------------------------------------------------------------
@pytest.fixture
def vault(tmp_path, monkeypatch):
    monkeypatch.setenv("ECO_MASTER_KEY", "test-master-key-测试主密钥")
    return FileVaultBackend(tmp_path / "keystore.enc")


class TestFileVaultBackend:
    def test_crud_roundtrip(self, vault):
        assert vault.get("MOONSHOT_API_KEY") is None
        vault.set("MOONSHOT_API_KEY", "sk-secret-值")
        assert vault.get("MOONSHOT_API_KEY") == "sk-secret-值"
        vault.set("OTHER_KEY", "v2")
        assert vault.list_keys() == ["MOONSHOT_API_KEY", "OTHER_KEY"]
        vault.delete("MOONSHOT_API_KEY")
        assert vault.get("MOONSHOT_API_KEY") is None
        assert vault.list_keys() == ["OTHER_KEY"]
        vault.delete("NOT_EXIST")  # 不存在不报错

    def test_ciphertext_not_plaintext(self, vault):
        vault.set("MY_KEY", "sk-plaintext-marker")
        raw = vault._path.read_text("utf-8")
        assert "sk-plaintext-marker" not in raw

    def test_file_mode_0600_on_write(self, vault):
        vault.set("K", "v")
        assert stat.S_IMODE(vault._path.stat().st_mode) == 0o600

    def test_mode_enforced_when_too_open(self, tmp_path, monkeypatch, caplog):
        monkeypatch.setenv("ECO_MASTER_KEY", "k")
        p = tmp_path / "open.enc"
        p.write_text("{}", encoding="utf-8")
        p.chmod(0o644)
        with caplog.at_level("WARNING", logger="keystore"):
            FileVaultBackend(p)
        assert stat.S_IMODE(p.stat().st_mode) == 0o600

    def test_pbkdf2_derivation_deterministic(self):
        k1 = FileVaultBackend._derive_key("same-key")
        k2 = FileVaultBackend._derive_key("same-key")
        k3 = FileVaultBackend._derive_key("other-key")
        assert k1 == k2 and len(k1) == 32
        assert k1 != k3

    def test_cross_instance_same_master_key(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ECO_MASTER_KEY", "shared-key")
        p = tmp_path / "ks.enc"
        FileVaultBackend(p).set("A_KEY", "v-shared")
        assert FileVaultBackend(p).get("A_KEY") == "v-shared"

    def test_wrong_master_key_refuses_read(self, tmp_path, monkeypatch, caplog):
        monkeypatch.setenv("ECO_MASTER_KEY", "right-key")
        p = tmp_path / "ks.enc"
        FileVaultBackend(p).set("A_KEY", "v")
        monkeypatch.setenv("ECO_MASTER_KEY", "wrong-key")
        with caplog.at_level("WARNING", logger="keystore"):
            assert FileVaultBackend(p).get("A_KEY") is None

    def test_missing_master_key_raises(self, tmp_path, monkeypatch):
        monkeypatch.delenv("ECO_MASTER_KEY", raising=False)
        with pytest.raises(RuntimeError, match="ECO_MASTER_KEY"):
            FileVaultBackend(tmp_path / "ks.enc")

    def test_no_crypto_refuses_downgrade(self, tmp_path, monkeypatch):
        monkeypatch.setattr(keystore, "CRYPTO_AVAIL", False)
        monkeypatch.setenv("ECO_MASTER_KEY", "k")
        with pytest.raises(RuntimeError, match="拒绝静默降级"):
            FileVaultBackend(tmp_path / "ks.enc")


# ---------------------------------------------------------------------------
# VaultClientBackend
# ---------------------------------------------------------------------------
def _mock_http(store):
    """模拟 Vault KV v2：store 为 (path -> value) dict"""

    def http(req: urllib.request.Request, timeout: int) -> bytes:
        assert req.get_header("X-vault-token") == "tok-mock"
        url = req.full_url
        path = url.split("/v1/", 1)[1]
        data_prefix = "secret/data/"
        meta_prefix = "secret/metadata"
        if req.get_method() == "GET" and path.startswith(data_prefix):
            key = path[len(data_prefix) :]
            if key not in store:
                raise urllib.error.HTTPError(url, 404, "not found", {}, io.BytesIO(b""))
            return json.dumps({"data": {"data": {"value": store[key]}}}).encode()
        if req.get_method() == "POST" and path.startswith(data_prefix):
            key = path[len(data_prefix) :]
            store[key] = json.loads(req.data.decode())["data"]["value"]
            return b"{}"
        if req.get_method() == "DELETE" and path.startswith(data_prefix):
            store.pop(path[len(data_prefix) :], None)
            return b""
        if req.get_method() == "LIST" and path == meta_prefix:
            return json.dumps({"data": {"keys": sorted(store)}}).encode()
        raise AssertionError(f"未预期的请求: {req.get_method()} {url}")

    return http


class TestVaultClientBackend:
    @pytest.fixture
    def client(self):
        store = {}
        return VaultClientBackend(addr="http://vault.test:8200", token="tok-mock", http_fn=_mock_http(store)), store

    def test_crud(self, client):
        c, store = client
        assert c.get("K") is None
        c.set("K", "v1")
        assert c.get("K") == "v1"
        assert store["K"] == "v1"  # 确实走了 HTTP 层
        c.delete("K")
        assert c.get("K") is None

    def test_list_keys(self, client):
        c, _ = client
        c.set("B_KEY", "1")
        c.set("A_KEY", "2")
        assert c.list_keys() == ["A_KEY", "B_KEY"]

    def test_env_addr_fallback(self, monkeypatch):
        monkeypatch.setenv("VAULT_ADDR", "http://env-vault:8200/")
        monkeypatch.setenv("VAULT_TOKEN", "tok-env")
        c = VaultClientBackend(http_fn=lambda req, t: b"{}")
        assert c._addr == "http://env-vault:8200"
        assert c._token == "tok-env"

    def test_missing_addr_raises(self, monkeypatch):
        monkeypatch.delenv("VAULT_ADDR", raising=False)
        with pytest.raises(RuntimeError, match="VAULT_ADDR"):
            VaultClientBackend()


# ---------------------------------------------------------------------------
# get_keystore 工厂
# ---------------------------------------------------------------------------
class TestGetKeystore:
    def test_default_env(self, monkeypatch):
        monkeypatch.delenv("ECO_SECRET_BACKEND", raising=False)
        assert isinstance(get_keystore(), EnvBackend)

    def test_select_by_env(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ECO_SECRET_BACKEND", "file")
        monkeypatch.setenv("ECO_MASTER_KEY", "k")
        monkeypatch.setattr(keystore, "DEFAULT_VAULT_FILE", tmp_path / "ks.enc")
        assert isinstance(get_keystore(), FileVaultBackend)
        monkeypatch.setenv("ECO_SECRET_BACKEND", "vault")
        monkeypatch.setenv("VAULT_ADDR", "http://v:8200")
        assert isinstance(get_keystore(), VaultClientBackend)

    def test_unknown_falls_back_env(self, monkeypatch, caplog):
        monkeypatch.setenv("ECO_SECRET_BACKEND", "bogus")
        with caplog.at_level("WARNING", logger="keystore"):
            assert isinstance(get_keystore(), EnvBackend)


# ---------------------------------------------------------------------------
# llm_providers 集成：keystore 优先 + env 回退
# ---------------------------------------------------------------------------
class TestLLMProvidersIntegration:
    def test_keystore_first_then_env(self, tmp_path, monkeypatch):
        """keystore(file) 有 key 而 os.environ 没有 → resolve 命中"""
        monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
        monkeypatch.delenv("KIMI_API_KEY", raising=False)
        monkeypatch.delenv("ECO_LLM_PROVIDER", raising=False)
        monkeypatch.setenv("ECO_SECRET_BACKEND", "file")
        monkeypatch.setenv("ECO_MASTER_KEY", "k")
        monkeypatch.setattr(keystore, "DEFAULT_VAULT_FILE", tmp_path / "ks.enc")
        ks = get_keystore()
        ks.set("MOONSHOT_API_KEY", "sk-from-vault")
        assert lp.resolve_provider(None).name == "moonshot"
        assert lp.get_provider("moonshot").has_key()

    def test_env_direct_read_still_works(self, monkeypatch):
        """默认 env 后端：os.environ 直读行为不变"""
        monkeypatch.delenv("ECO_SECRET_BACKEND", raising=False)
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-env-direct")
        monkeypatch.delenv("KIMI_API_KEY", raising=False)
        monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
        monkeypatch.delenv("ECO_LLM_PROVIDER", raising=False)
        assert lp.resolve_provider(None).name == "deepseek"

    def test_backend_failure_falls_back_env(self, monkeypatch):
        """keystore 后端炸掉 → 静默回退 os.environ"""
        monkeypatch.setenv("ECO_SECRET_BACKEND", "file")
        monkeypatch.delenv("ECO_MASTER_KEY", raising=False)  # file 后端必然构造失败
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-fallback")
        monkeypatch.delenv("KIMI_API_KEY", raising=False)
        monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
        monkeypatch.delenv("ECO_LLM_PROVIDER", raising=False)
        assert lp.resolve_provider(None).name == "deepseek"

    def test_explicit_env_dict_bypasses_keystore(self, monkeypatch):
        """显式 env dict 是纯 env 语义，不查 keystore"""
        monkeypatch.setenv("ECO_SECRET_BACKEND", "bogus-backend")
        spec = lp.get_provider("moonshot")
        assert spec.has_key({"MOONSHOT_API_KEY": "x"})
        assert not spec.has_key({})
