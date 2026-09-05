"""SecureStore 凭证加密存储测试——加密往返/拒绝降级/密钥来源/错误密钥拒读"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
import pytest

import agent_core.connector_system as cs


@pytest.fixture
def store(tmp_path, monkeypatch):
    """隔离数据目录 + 固定主密钥的 SecureStore"""
    monkeypatch.setattr(cs, "DATA_DIR", tmp_path)
    monkeypatch.setenv("ECO_MASTER_KEY", "test-master-key-统一密钥")
    return cs.SecureStore(), tmp_path


class TestSecureStore:
    def test_encrypt_decrypt_roundtrip(self, store):
        s, tmp = store
        creds = {"token": "ghp_secret_token_123", "user": "agent"}
        s.save("github", creds)
        s._cache.clear()  # 清缓存，强制走磁盘解密路径
        assert s.load("github") == creds

    def test_ciphertext_on_disk_not_plaintext(self, store):
        s, tmp = store
        s.save("github", {"token": "ghp_secret_token_123"})
        raw = (tmp / "vault.enc").read_text("utf-8")
        assert "ghp_secret_token_123" not in raw, "磁盘上不得出现明文凭证"
        assert "github" in raw  # 服务名作为键可以明文

    def test_wrong_key_cannot_decrypt(self, store, monkeypatch):
        s, tmp = store
        s.save("github", {"token": "ghp_secret_token_123"})
        monkeypatch.setenv("ECO_MASTER_KEY", "另一把错误的密钥")
        s2 = cs.SecureStore()  # 新实例，缓存为空
        assert s2.load("github") is None, "错误密钥必须拒读，不得返回明文或残缺数据"

    def test_refuse_downgrade_without_crypto(self, monkeypatch, tmp_path):
        """cryptography 不可用：必须抛错拒绝静默降级为明文存储（S-02 红线）"""
        monkeypatch.setattr(cs, "DATA_DIR", tmp_path)
        monkeypatch.setattr(cs, "CRYPTO_AVAIL", False)
        with pytest.raises(RuntimeError, match="拒绝静默降级"):
            cs.SecureStore()

    def test_key_source_env(self, tmp_path, monkeypatch):
        """ECO_MASTER_KEY 是两个实例共享密文的密钥来源"""
        monkeypatch.setattr(cs, "DATA_DIR", tmp_path)
        monkeypatch.setenv("ECO_MASTER_KEY", "shared-env-key")
        s1 = cs.SecureStore()
        s1.save("feishu", {"token": "t_env"})
        s2 = cs.SecureStore()  # 同 env，无缓存
        assert s2.load("feishu") == {"token": "t_env"}, "同一 ECO_MASTER_KEY 必须能互相解密"

    def test_temp_key_warns_when_env_missing(self, tmp_path, monkeypatch, caplog):
        """未配置 ECO_MASTER_KEY：生成随机临时密钥并给出醒目告警"""
        monkeypatch.setattr(cs, "DATA_DIR", tmp_path)
        monkeypatch.delenv("ECO_MASTER_KEY", raising=False)
        with caplog.at_level("WARNING", logger="connector_system"):
            s = cs.SecureStore()
        assert any("临时主密钥" in r.message for r in caplog.records)
        # 临时密钥实例自身仍可加密往返
        s.save("x", {"token": "t"})
        s._cache.clear()
        assert s.load("x") == {"token": "t"}

    def test_delete_removes_entry(self, store):
        s, tmp = store
        s.save("github", {"token": "t"})
        s.delete("github")
        s._cache.clear()
        assert s.load("github") is None
        assert "github" not in (tmp / "vault.enc").read_text("utf-8")


class TestConnectorManager:
    def test_connect_verify_and_disconnect(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cs, "DATA_DIR", tmp_path)
        monkeypatch.setenv("ECO_MASTER_KEY", "cm-test-key")
        cm = cs.ConnectorManager()
        r = cm.connect("github", {"token": "abc"})
        assert r == {"success": True, "service": "github"}
        assert any(c["id"] == "github" and c["connected"] for c in cm.list_all())
        # 无凭证字段必须验证失败
        r2 = cm.connect("gitlab", {"note": "没有token"})
        assert r2["success"] is False
        # 未知服务拒绝
        assert cm.connect("不存在的服务", {"token": "x"})["success"] is False
        assert cm.disconnect("github")["success"] is True
        assert not any(c["id"] == "github" and c["connected"] for c in cm.list_all())

    def test_registry_size_and_categories(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cs, "DATA_DIR", tmp_path)
        monkeypatch.setenv("ECO_MASTER_KEY", "cm-test-key")
        cm = cs.ConnectorManager()
        stats = cm.get_stats()
        assert stats["total"] >= 50
        assert stats["categories"] >= 11
        # 注册表无重复 id
        ids = [c.id for c in cs.CONNECTOR_REGISTRY]
        assert len(ids) == len(set(ids))
