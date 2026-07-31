#!/usr/bin/env python3
"""sso.py — SSO/OIDC（含 CAS 3.0 简化）统一认证对接，与 RBAC 联动

政务内网常见 OIDC / CAS 协议接入：
  - OIDCConfig：issuer/client_id/redirect_uri/scopes/role_claim/enabled；
    client_secret 一律经 keystore（ECO_SSO_CLIENT_SECRET）读取，不落明文。
  - OIDCProvider：discovery（urllib，可注入 http_fn mock）、授权 URL 生成
    （state=SM3(随机) 防 CSRF）、code 换 token、id_token RS256 验签
    （JWKS + cryptography；alg=none 一律拒绝）、claims 提取。
  - map_role()：role_claim → rbac.Role；映射表可由 env ECO_SSO_ROLE_MAP
    （JSON {"sso角色": "本地角色"}）配置；未知角色降级 readonly_visitor。
  - 本地会话：登录成功签发 SM3 签名 + TTL 的会话 token（复用 grants 本机
    密钥风格），verify_session() 校验签名与过期。
  - CAS：ECO_SSO_PROTOCOL=cas 时走 CAS 3.0 serviceValidate（XML 解析）。

门控：ECO_SSO=1 启用；默认关闭，所有能力不生效，不影响现有行为。
铁律：本文件不含任何真实 key/secret；HTTP 一律 urllib 且可注入 mock。
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import secrets as _secrets
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from agent_core import grants as grants_mod
from agent_core import keystore as keystore_mod
from agent_core import rbac

log = logging.getLogger("eco.sso")

try:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric import padding, rsa
    from cryptography.hazmat.primitives.hashes import SHA256
    CRYPTO_AVAIL = True
except Exception:  # pragma: no cover - cryptography 缺失时拒绝验签
    CRYPTO_AVAIL = False

DEFAULT_SESSION_TTL = 8 * 3600  # 会话默认 8 小时
SECRET_KEY_NAME = "ECO_SSO_CLIENT_SECRET"


def _sm3(text: str) -> str:
    return hashlib.new("sm3", text.encode("utf-8")).hexdigest()


def _b64url_decode(s: str) -> bytes:
    s += "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s.encode("ascii"))


def _b64url_encode(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def sso_enabled() -> bool:
    return os.environ.get("ECO_SSO", "").strip() in ("1", "true", "yes", "on")


def sso_protocol() -> str:
    return os.environ.get("ECO_SSO_PROTOCOL", "oidc").strip().lower() or "oidc"


@dataclass
class OIDCConfig:
    """SSO/OIDC 配置。client_secret 经 keystore 读取（不落明文字段）。"""
    issuer: str = ""
    client_id: str = ""
    redirect_uri: str = ""
    scopes: tuple[str, ...] = ("openid", "profile")
    role_claim: str = "role"
    enabled: bool = False
    protocol: str = "oidc"           # oidc | cas
    cas_validate_url: str = ""       # CAS 模式：{cas}/p3/serviceValidate
    session_ttl: int = DEFAULT_SESSION_TTL
    _client_secret: str = field(default="", repr=False)

    @property
    def client_secret(self) -> str:
        return self._client_secret

    @classmethod
    def from_env(cls, keystore=None) -> OIDCConfig:
        ks = keystore if keystore is not None else keystore_mod.get_keystore()
        try:
            secret = ks.get(SECRET_KEY_NAME) or ""
        except Exception:
            secret = ""
        scopes = tuple(s for s in os.environ.get(
            "ECO_SSO_SCOPES", "openid profile").split() if s)
        return cls(
            issuer=os.environ.get("ECO_SSO_ISSUER", "").rstrip("/"),
            client_id=os.environ.get("ECO_SSO_CLIENT_ID", ""),
            redirect_uri=os.environ.get("ECO_SSO_REDIRECT_URI", ""),
            scopes=scopes or ("openid", "profile"),
            role_claim=os.environ.get("ECO_SSO_ROLE_CLAIM", "role"),
            enabled=sso_enabled(),
            protocol=sso_protocol(),
            cas_validate_url=os.environ.get("ECO_SSO_CAS_VALIDATE_URL", ""),
            session_ttl=int(os.environ.get("ECO_SSO_SESSION_TTL",
                                           DEFAULT_SESSION_TTL)),
            _client_secret=secret,
        )

    def masked_secret(self) -> str:
        if not self._client_secret:
            return "(未配置)"
        return self._client_secret[:2] + "***" + self._client_secret[-2:] \
            if len(self._client_secret) > 4 else "***"


class SSOError(Exception):
    """SSO 协议/验签错误"""


class OIDCProvider:
    """OIDC 提供方客户端。http_fn(req, timeout) -> bytes 可注入 mock。"""

    def __init__(self, config: OIDCConfig, http_fn=None, timeout: int = 5):
        self.config = config
        self._http = http_fn or self._default_http
        self._timeout = timeout
        self._discovery: dict | None = None
        self._pending_states: set[str] = set()

    @staticmethod
    def _default_http(req: urllib.request.Request, timeout: int) -> bytes:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()

    def _get_json(self, url: str) -> dict:
        req = urllib.request.Request(url, method="GET")
        body = self._http(req, self._timeout)
        return json.loads(body.decode("utf-8"))

    # ------------------------------------------------------------------
    # discovery
    # ------------------------------------------------------------------
    def discover(self, force: bool = False) -> dict:
        """GET {issuer}/.well-known/openid-configuration（带缓存）"""
        if self._discovery is not None and not force:
            return self._discovery
        if not self.config.issuer:
            raise SSOError("未配置 issuer")
        url = f"{self.config.issuer}/.well-known/openid-configuration"
        doc = self._get_json(url)
        if not isinstance(doc, dict) or "authorization_endpoint" not in doc:
            raise SSOError("discovery 文档缺少 authorization_endpoint")
        self._discovery = doc
        return doc

    # ------------------------------------------------------------------
    # 授权 URL（state 防 CSRF）
    # ------------------------------------------------------------------
    def authorization_url(self, state: str | None = None,
                          extra: dict | None = None) -> tuple[str, str]:
        """生成授权跳转 URL。state 缺省生成 SM3(随机) 并登记待校验。
        返回 (url, state)。"""
        ep = self.discover()["authorization_endpoint"]
        if state is None:
            state = _sm3(_secrets.token_hex(32))
        self._pending_states.add(state)
        q = {
            "response_type": "code",
            "client_id": self.config.client_id,
            "redirect_uri": self.config.redirect_uri,
            "scope": " ".join(self.config.scopes),
            "state": state,
        }
        if extra:
            q.update(extra)
        return f"{ep}?{urllib.parse.urlencode(q)}", state

    def check_state(self, state: str) -> bool:
        """校验回调 state（一次性消费）"""
        if state and state in self._pending_states:
            self._pending_states.discard(state)
            return True
        return False

    # ------------------------------------------------------------------
    # code 换 token
    # ------------------------------------------------------------------
    def exchange_code(self, code: str) -> dict:
        ep = self.discover()["token_endpoint"]
        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.config.redirect_uri,
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
        }
        req = urllib.request.Request(
            ep, data=urllib.parse.urlencode(payload).encode("utf-8"),
            method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        body = self._http(req, self._timeout)
        tok = json.loads(body.decode("utf-8"))
        if "id_token" not in tok:
            raise SSOError("token 响应缺少 id_token")
        return tok

    # ------------------------------------------------------------------
    # id_token 验签（RS256 + JWKS；alg=none 拒绝）
    # ------------------------------------------------------------------
    def _jwks(self) -> dict:
        uri = self.discover().get("jwks_uri")
        if not uri:
            raise SSOError("discovery 缺少 jwks_uri")
        return self._get_json(uri)

    def verify_id_token(self, id_token: str) -> dict:
        """验签并提取 claims（sub/name/role_claim）。失败抛 SSOError。"""
        try:
            h, p, s = id_token.split(".")
        except ValueError as e:
            raise SSOError("id_token 格式非法（非三段 JWT）") from e
        try:
            header = json.loads(_b64url_decode(h))
            claims = json.loads(_b64url_decode(p))
        except (ValueError, UnicodeDecodeError) as e:
            raise SSOError("id_token header/payload 解码失败") from e
        alg = header.get("alg", "")
        if alg.lower() == "none" or alg != "RS256":
            raise SSOError(f"不允许的签名算法: {alg or '(缺失)'}（仅 RS256）")
        if not CRYPTO_AVAIL:
            raise SSOError("cryptography 不可用，拒绝验签")

        key = self._select_jwk(header.get("kid"))
        numbers = rsa.RSAPublicNumbers(
            e=int.from_bytes(_b64url_decode(key["e"]), "big"),
            n=int.from_bytes(_b64url_decode(key["n"]), "big"),
        )
        pub = numbers.public_key()
        try:
            pub.verify(_b64url_decode(s), f"{h}.{p}".encode("ascii"),
                       padding.PKCS1v15(), SHA256())
        except InvalidSignature as e:
            raise SSOError("id_token 签名无效") from e

        exp = claims.get("exp")
        if exp is not None and time.time() > float(exp):
            raise SSOError("id_token 已过期")
        if claims.get("iss") and self.config.issuer \
                and claims["iss"].rstrip("/") != self.config.issuer.rstrip("/"):
            raise SSOError("id_token iss 与 issuer 不匹配")
        return claims

    def _select_jwk(self, kid: str | None) -> dict:
        keys = (self._jwks() or {}).get("keys", [])
        for k in keys:
            if k.get("kty") == "RSA" and (kid is None or k.get("kid") == kid):
                return k
        raise SSOError(f"JWKS 中找不到匹配 kid={kid} 的 RSA 公钥")

    def extract_claims(self, claims: dict) -> dict:
        """提取标准化身份字段"""
        return {
            "sub": claims.get("sub", ""),
            "name": claims.get("name") or claims.get("preferred_username", ""),
            "role_claim": claims.get(self.config.role_claim, ""),
        }


# ---------------------------------------------------------------------------
# 角色映射（与 RBAC 联动）
# ---------------------------------------------------------------------------
def _role_map() -> dict:
    raw = os.environ.get("ECO_SSO_ROLE_MAP", "").strip()
    if not raw:
        return {}
    try:
        m = json.loads(raw)
        return m if isinstance(m, dict) else {}
    except json.JSONDecodeError:
        log.warning("[sso] ECO_SSO_ROLE_MAP 不是合法 JSON，忽略")
        return {}


def map_role(claims: dict, role_claim: str = "role") -> rbac.Role:
    """role_claim → rbac.Role。先查 ECO_SSO_ROLE_MAP 配置映射，
    再尝试直接按本地角色名匹配，未知角色一律降级 readonly_visitor。"""
    value = str(claims.get(role_claim, "") or "").strip()
    if value:
        mapped = _role_map().get(value, value)
        r = rbac._coerce_role(mapped)
        if r is not None:
            return r
        log.warning("[sso] 未知 SSO 角色 %r，降级 readonly_visitor", value)
    return rbac.Role.READONLY_VISITOR


# ---------------------------------------------------------------------------
# 本地会话 token（SM3 签名 + TTL，复用 grants 本机密钥风格）
# ---------------------------------------------------------------------------
def _session_sign(payload_b64: str) -> str:
    return _sm3(grants_mod._secret() + "|sso|" + payload_b64)


def issue_session(identity: dict, role, ttl: int | None = None) -> str:
    """登录成功签发本地会话 token：b64url(body).sm3sig"""
    ttl = int(ttl if ttl is not None else DEFAULT_SESSION_TTL)
    r = rbac._coerce_role(role) or rbac.Role.READONLY_VISITOR
    body = {
        "sub": identity.get("sub", ""),
        "name": identity.get("name", ""),
        "role": r.value,
        "iat": time.time(),
        "expires_at": time.time() + ttl,
    }
    payload = _b64url_encode(json.dumps(body, ensure_ascii=False).encode("utf-8"))
    return f"{payload}.{_session_sign(payload)}"


def verify_session(token: str) -> dict | None:
    """校验会话 token（签名 + TTL）。有效返回会话 dict，否则 None。"""
    if not token or "." not in token:
        return None
    payload, sig = token.rsplit(".", 1)
    if not _secrets.compare_digest(_session_sign(payload), sig):
        return None
    try:
        body = json.loads(_b64url_decode(payload))
    except (ValueError, UnicodeDecodeError):
        return None
    if time.time() > float(body.get("expires_at", 0)):
        return None
    return body


# ---------------------------------------------------------------------------
# CAS 3.0 简化支持（serviceValidate XML 解析）
# ---------------------------------------------------------------------------
_CAS_NS = "{http://www.yale.edu/tp/cas}"


def cas_validate(ticket: str, service: str, validate_url: str = "",
                 http_fn=None, timeout: int = 5) -> dict:
    """CAS 3.0 (/p3/serviceValidate) 校验。成功返回
    {"sub": user, "attributes": {...}}；失败抛 SSOError。"""
    url = validate_url or os.environ.get("ECO_SSO_CAS_VALIDATE_URL", "")
    if not url:
        raise SSOError("未配置 CAS validate URL")
    q = urllib.parse.urlencode({"ticket": ticket, "service": service})
    req = urllib.request.Request(f"{url}?{q}", method="GET")
    http = http_fn or OIDCProvider._default_http
    body = http(req, timeout)
    return parse_cas_validate_xml(body)


def parse_cas_validate_xml(data: bytes | str) -> dict:
    """解析 CAS serviceValidate 响应 XML：
    成功 → {"sub": user, "attributes": {...}}；失败 → SSOError。"""
    text = data.decode("utf-8") if isinstance(data, bytes) else data
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        raise SSOError("CAS 响应不是合法 XML") from e
    failure = root.find(f"{_CAS_NS}authenticationFailure")
    if failure is None:
        failure = root.find("authenticationFailure")
    if failure is not None:
        raise SSOError(
            f"CAS 认证失败: {failure.get('code', '')} {(failure.text or '').strip()}")
    success = root.find(f"{_CAS_NS}authenticationSuccess")
    if success is None:
        success = root.find("authenticationSuccess")
    if success is None:
        raise SSOError("CAS 响应缺少 authenticationSuccess")
    user_el = success.find(f"{_CAS_NS}user")
    if user_el is None:
        user_el = success.find("user")
    user = (user_el.text or "").strip() if user_el is not None else ""
    if not user:
        raise SSOError("CAS 响应缺少 user")
    attrs: dict = {}
    attrs_el = success.find(f"{_CAS_NS}attributes")
    if attrs_el is None:
        attrs_el = success.find("attributes")
    if attrs_el is not None:
        for child in attrs_el:
            tag = child.tag.replace(_CAS_NS, "")
            attrs.setdefault(tag, (child.text or "").strip())
    return {"sub": user, "name": attrs.get("cn") or attrs.get("name") or user,
            "attributes": attrs}
