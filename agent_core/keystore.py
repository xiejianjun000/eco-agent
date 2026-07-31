#!/usr/bin/env python3
"""keystore.py - 秘钥管理生产化（SPEC-r13 任务 D）

统一秘钥后端抽象：
  SecretBackend ABC（get/set/delete/list_keys）
  ├─ EnvBackend          现状兼容默认：直读/直写 os.environ
  ├─ FileVaultBackend    age 式加密文件库：AES-GCM + ECO_MASTER_KEY 派生 PBKDF2，0600 强制
  └─ VaultClientBackend  HashiCorp Vault HTTP 客户端（urllib，VAULT_ADDR/VAULT_TOKEN，可 mock）

get_keystore() 按 ECO_SECRET_BACKEND=env|file|vault 选择，默认 env。

铁律：本文件不含任何真实 key；HTTP 一律 urllib；后端故障时调用方自行回退。
"""
import base64
import json
import logging
import os
import stat
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from pathlib import Path

logger = logging.getLogger("keystore")

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    CRYPTO_AVAIL = True
except Exception:  # pragma: no cover - cryptography 缺失时拒绝降级
    CRYPTO_AVAIL = False

# 秘钥命名约定（list_keys 过滤用）
SECRET_ENV_SUFFIXES = ("_KEY", "_TOKEN", "_SECRET")

# FileVault 默认路径
DEFAULT_VAULT_FILE = Path.home() / ".eco" / "keystore.enc"
VAULT_FILE_MODE = 0o600

# PBKDF2 参数（固定 salt 使同一 ECO_MASTER_KEY 可重复解密；随机化由 GCM nonce 承担）
_PBKDF2_SALT = b"eco-keystore-v1"
_PBKDF2_ITERATIONS = 200_000
_NONCE_LEN = 12


class SecretBackend(ABC):
    """秘钥后端抽象基类"""

    @abstractmethod
    def get(self, key: str) -> str | None:
        """取秘钥；不存在返回 None"""

    @abstractmethod
    def set(self, key: str, value: str) -> None:
        """写秘钥"""

    @abstractmethod
    def delete(self, key: str) -> None:
        """删秘钥（不存在不报错）"""

    @abstractmethod
    def list_keys(self) -> list[str]:
        """列出所有秘钥名（不返回值）"""


# ---------------------------------------------------------------------------
# EnvBackend：现状兼容默认
# ---------------------------------------------------------------------------
class EnvBackend(SecretBackend):
    """直读 os.environ——与历史行为完全一致"""

    def __init__(self, env: dict | None = None):
        self._env = os.environ if env is None else env

    def get(self, key: str) -> str | None:
        return self._env.get(key) or None

    def set(self, key: str, value: str) -> None:
        self._env[key] = value

    def delete(self, key: str) -> None:
        self._env.pop(key, None)

    def list_keys(self) -> list[str]:
        return sorted(
            k for k, v in self._env.items()
            if v and k.endswith(SECRET_ENV_SUFFIXES)
        )


# ---------------------------------------------------------------------------
# FileVaultBackend：AES-GCM 加密文件库
# ---------------------------------------------------------------------------
class FileVaultBackend(SecretBackend):
    """age 式加密文件库。

    主密钥：ECO_MASTER_KEY 经 PBKDF2-HMAC-SHA256 派生 32 字节 AES 密钥；
    每条秘钥独立随机 nonce 做 AES-GCM，密文 base64 存 JSON 单文件；
    文件权限强制 0600（写入时 chmod，发现权限过宽时告警并收紧）。
    """

    def __init__(self, path: str | Path | None = None, master_key: str = ""):
        if not CRYPTO_AVAIL:
            raise RuntimeError("[FileVaultBackend] cryptography 库不可用，已拒绝静默降级为明文存储")
        if not master_key:
            master_key = os.environ.get("ECO_MASTER_KEY", "")
        if not master_key:
            raise RuntimeError(
                "[FileVaultBackend] 未设置 ECO_MASTER_KEY，拒绝创建加密秘钥库——"
                "请先配置长期随机主密钥"
            )
        self._path = Path(path) if path else DEFAULT_VAULT_FILE
        self._key = self._derive_key(master_key)
        self._aead = AESGCM(self._key)
        if self._path.exists():
            self._enforce_mode(self._path)

    @staticmethod
    def _derive_key(master_key: str) -> bytes:
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=_PBKDF2_SALT,
            iterations=_PBKDF2_ITERATIONS,
        )
        return kdf.derive(master_key.encode("utf-8"))

    @staticmethod
    def _enforce_mode(path: Path) -> None:
        mode = stat.S_IMODE(path.stat().st_mode)
        if mode != VAULT_FILE_MODE:
            logger.warning(
                "[FileVaultBackend] %s 权限 %03o 过宽，已收紧为 600", path, mode
            )
            path.chmod(VAULT_FILE_MODE)

    def _read_db(self) -> dict:
        if not self._path.exists():
            return {}
        try:
            return json.loads(self._path.read_text("utf-8", errors="replace"))
        except (json.JSONDecodeError, OSError):
            logger.error("[FileVaultBackend] 秘钥库文件损坏或不可读: %s", self._path)
            return {}

    def _write_db(self, db: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(db, ensure_ascii=False), encoding="utf-8")
        self._path.chmod(VAULT_FILE_MODE)

    def get(self, key: str) -> str | None:
        entry = self._read_db().get(key)
        if not entry:
            return None
        try:
            blob = base64.b64decode(entry.encode())
            nonce, ct = blob[:_NONCE_LEN], blob[_NONCE_LEN:]
            return self._aead.decrypt(nonce, ct, None).decode("utf-8")
        except Exception:
            logger.warning("[FileVaultBackend] %s 解密失败（密钥错误？），拒读", key)
            return None

    def set(self, key: str, value: str) -> None:
        nonce = os.urandom(_NONCE_LEN)
        ct = self._aead.encrypt(nonce, value.encode("utf-8"), None)
        db = self._read_db()
        db[key] = base64.b64encode(nonce + ct).decode()
        self._write_db(db)

    def delete(self, key: str) -> None:
        db = self._read_db()
        if key in db:
            db.pop(key)
            self._write_db(db)

    def list_keys(self) -> list[str]:
        return sorted(self._read_db().keys())


# ---------------------------------------------------------------------------
# VaultClientBackend：HashiCorp Vault KV v2 HTTP 客户端
# ---------------------------------------------------------------------------
class VaultClientBackend(SecretBackend):
    """HashiCorp Vault（KV v2 引擎）HTTP 客户端。

    端点：<VAULT_ADDR>/v1/<mount>/data/<key>（mount 默认 secret）
    认证：X-Vault-Token: <VAULT_TOKEN>
    秘钥值存于 data.data.value。
    http_fn 可注入（测试 mock），签名 http_fn(req: urllib.request.Request, timeout: int) -> bytes
    """

    def __init__(
        self,
        addr: str = "",
        token: str = "",
        mount: str = "secret",
        timeout: int = 5,
        http_fn=None,
    ):
        self._addr = (addr or os.environ.get("VAULT_ADDR", "")).rstrip("/")
        self._token = token or os.environ.get("VAULT_TOKEN", "")
        if not self._addr:
            raise RuntimeError("[VaultClientBackend] 未配置 VAULT_ADDR")
        self._mount = mount
        self._timeout = timeout
        self._http = http_fn or self._default_http

    @staticmethod
    def _default_http(req: urllib.request.Request, timeout: int) -> bytes:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()

    def _request(self, method: str, path: str, payload: dict | None = None) -> dict:
        url = f"{self._addr}/v1/{path}"
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("X-Vault-Token", self._token)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        body = self._http(req, self._timeout)
        return json.loads(body.decode("utf-8")) if body else {}

    def _data_path(self, key: str) -> str:
        return f"{self._mount}/data/{key}"

    def get(self, key: str) -> str | None:
        try:
            resp = self._request("GET", self._data_path(key))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            raise
        return (resp.get("data") or {}).get("data", {}).get("value")

    def set(self, key: str, value: str) -> None:
        self._request("POST", self._data_path(key), {"data": {"value": value}})

    def delete(self, key: str) -> None:
        try:
            self._request("DELETE", self._data_path(key))
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise

    def list_keys(self) -> list[str]:
        try:
            resp = self._request("LIST", f"{self._mount}/metadata")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return []
            raise
        return sorted((resp.get("data") or {}).get("keys", []))


# ---------------------------------------------------------------------------
# 工厂
# ---------------------------------------------------------------------------
_BACKENDS = {"env": EnvBackend, "file": FileVaultBackend, "vault": VaultClientBackend}


def get_keystore(backend: str | None = None) -> SecretBackend:
    """按 ECO_SECRET_BACKEND=env|file|vault 选择后端；默认 env（现状兼容）。

    backend 显式传参优先于环境变量（测试/集成注入用）。
    """
    name = (backend or os.environ.get("ECO_SECRET_BACKEND", "env")).strip().lower()
    cls = _BACKENDS.get(name)
    if cls is None:
        logger.warning(
            "[keystore] 未知 ECO_SECRET_BACKEND=%r，回退 env；可用: %s",
            name, "/".join(sorted(_BACKENDS)),
        )
        cls = EnvBackend
    return cls()
