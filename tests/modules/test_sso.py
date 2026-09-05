"""SSO/OIDC + CAS 统一认证测试：全 mock、零外呼。

覆盖：OIDCConfig/env 门控、discovery、授权 URL + state 防 CSRF、code 换
token、JWKS RS256 验签（cryptography 生成测试 RSA 密钥对）、alg=none
拒绝、角色映射（含 ECO_SSO_ROLE_MAP 与未知降级）、会话签发/验证/TTL
过期、gateway /auth/login 302 与 /auth/callback 全流程、/channels 管理
请求会话门控与回调豁免、CAS serviceValidate XML 解析、CLI sso status。
"""

import base64
import json
import time
import urllib.request

import pytest

from agent_core import grants as grants_mod
from agent_core import rbac
from agent_core import sso as sso_mod
from agent_core.channels import http_server

ISSUER = "https://idp.example.gov"
DISCOVERY = {
    "issuer": ISSUER,
    "authorization_endpoint": f"{ISSUER}/authorize",
    "token_endpoint": f"{ISSUER}/token",
    "jwks_uri": f"{ISSUER}/jwks",
}


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


@pytest.fixture()
def cfg():
    return sso_mod.OIDCConfig(
        issuer=ISSUER,
        client_id="eco-agent",
        redirect_uri="http://gw/auth/callback",
        scopes=("openid", "profile"),
        role_claim="role",
        enabled=True,
        _client_secret="test-secret-xxxx",
    )


def _make_provider(cfg, routes):
    """routes: {url: dict|bytes}；POST 按 URL 匹配。"""

    def http(req: urllib.request.Request, timeout: int):
        url = req.full_url
        if url not in routes:
            raise AssertionError(f"未预期的外呼: {url}")
        body = routes[url]
        return body if isinstance(body, bytes) else json.dumps(body).encode()

    return sso_mod.OIDCProvider(cfg, http_fn=http)


@pytest.fixture()
def rsa_keys():
    from cryptography.hazmat.primitives.asymmetric import rsa as _rsa

    priv = _rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub = priv.public_key().public_numbers()
    jwk = {
        "kty": "RSA",
        "kid": "k1",
        "n": _b64(pub.n.to_bytes((pub.n.bit_length() + 7) // 8, "big")),
        "e": _b64(pub.e.to_bytes((pub.e.bit_length() + 7) // 8, "big")),
    }
    return priv, jwk


def _jwt(priv, claims: dict, header: dict | None = None) -> str:
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives.hashes import SHA256

    h = {"alg": "RS256", "typ": "JWT", "kid": "k1"}
    if header:
        h.update(header)
    seg = f"{_b64(json.dumps(h).encode())}.{_b64(json.dumps(claims).encode())}"
    if h["alg"] == "none":
        return seg + "."
    sig = priv.sign(seg.encode(), padding.PKCS1v15(), SHA256())
    return f"{seg}.{_b64(sig)}"


CLAIMS = {"iss": ISSUER, "sub": "u-001", "name": "张三", "role": "commander", "exp": time.time() + 600}


# ---------------------------------------------------------------------------
# 配置与门控
# ---------------------------------------------------------------------------
class TestConfig:
    def test_gated_off_by_default(self, monkeypatch):
        monkeypatch.delenv("ECO_SSO", raising=False)
        assert not sso_mod.sso_enabled()

    def test_from_env(self, monkeypatch):
        from agent_core import keystore

        monkeypatch.setenv("ECO_SSO", "1")
        monkeypatch.setenv("ECO_SSO_ISSUER", ISSUER + "/")
        monkeypatch.setenv("ECO_SSO_CLIENT_ID", "eco")
        monkeypatch.setenv("ECO_SSO_CLIENT_SECRET", "abcdef123456")
        c = sso_mod.OIDCConfig.from_env(keystore=keystore.EnvBackend())
        assert c.enabled and c.issuer == ISSUER and c.client_secret == "abcdef123456"
        assert c.role_claim == "role"
        assert "***" in c.masked_secret() and "abcdef123456" not in c.masked_secret()


# ---------------------------------------------------------------------------
# discovery / 授权 URL / state
# ---------------------------------------------------------------------------
class TestOIDCFlow:
    def test_discovery(self, cfg):
        p = _make_provider(cfg, {f"{ISSUER}/.well-known/openid-configuration": DISCOVERY})
        doc = p.discover()
        assert doc["token_endpoint"] == DISCOVERY["token_endpoint"]
        assert p.discover() is doc  # 缓存

    def test_authorization_url_and_state(self, cfg):
        p = _make_provider(cfg, {f"{ISSUER}/.well-known/openid-configuration": DISCOVERY})
        url, state = p.authorization_url()
        assert url.startswith(f"{ISSUER}/authorize?")
        assert "response_type=code" in url and "client_id=eco-agent" in url
        assert f"state={state}" in url and len(state) == 64  # SM3 hexdigest
        assert p.check_state(state) is True
        assert p.check_state(state) is False  # 一次性消费

    def test_state_reject_unknown(self, cfg):
        p = _make_provider(cfg, {f"{ISSUER}/.well-known/openid-configuration": DISCOVERY})
        assert p.check_state("forged-state") is False

    def test_exchange_code(self, cfg):
        routes = {
            f"{ISSUER}/.well-known/openid-configuration": DISCOVERY,
            f"{ISSUER}/token": {"id_token": "x.y.z", "access_token": "a"},
        }
        p = _make_provider(cfg, routes)
        tok = p.exchange_code("code-123")
        assert tok["id_token"] == "x.y.z"


# ---------------------------------------------------------------------------
# JWKS 验签
# ---------------------------------------------------------------------------
class TestVerifyIdToken:
    def _provider(self, cfg, jwk, id_token):
        routes = {f"{ISSUER}/.well-known/openid-configuration": DISCOVERY, f"{ISSUER}/jwks": {"keys": [jwk]}}
        return _make_provider(cfg, routes)

    def test_rs256_ok(self, cfg, rsa_keys):
        priv, jwk = rsa_keys
        tok = _jwt(priv, CLAIMS)
        claims = self._provider(cfg, jwk, tok).verify_id_token(tok)
        assert claims["sub"] == "u-001" and claims["role"] == "commander"

    def test_alg_none_rejected(self, cfg, rsa_keys):
        priv, jwk = rsa_keys
        tok = _jwt(priv, CLAIMS, header={"alg": "none", "kid": None})
        with pytest.raises(sso_mod.SSOError, match="RS256"):
            self._provider(cfg, jwk, tok).verify_id_token(tok)

    def test_bad_signature_rejected(self, cfg, rsa_keys):
        priv, jwk = rsa_keys
        tok = _jwt(priv, CLAIMS)
        bad = tok.rsplit(".", 1)[0] + "." + _b64(b"forged")
        with pytest.raises(sso_mod.SSOError, match="签名无效"):
            self._provider(cfg, jwk, bad).verify_id_token(bad)

    def test_expired_token_rejected(self, cfg, rsa_keys):
        priv, jwk = rsa_keys
        claims = dict(CLAIMS, exp=time.time() - 10)
        tok = _jwt(priv, claims)
        with pytest.raises(sso_mod.SSOError, match="过期"):
            self._provider(cfg, jwk, tok).verify_id_token(tok)

    def test_issuer_mismatch_rejected(self, cfg, rsa_keys):
        priv, jwk = rsa_keys
        tok = _jwt(priv, dict(CLAIMS, iss="https://evil.example"))
        with pytest.raises(sso_mod.SSOError, match="iss"):
            self._provider(cfg, jwk, tok).verify_id_token(tok)

    def test_extract_claims(self, cfg):
        ident = sso_mod.OIDCProvider(cfg, http_fn=lambda *a: b"").extract_claims(CLAIMS)
        assert ident == {"sub": "u-001", "name": "张三", "role_claim": "commander"}


# ---------------------------------------------------------------------------
# 角色映射
# ---------------------------------------------------------------------------
class TestRoleMapping:
    def test_direct_role_name(self):
        assert sso_mod.map_role({"role": "admin"}) is rbac.Role.ADMIN
        assert sso_mod.map_role({"role": "执法员"}) is rbac.Role.ENFORCER

    def test_env_role_map(self, monkeypatch):
        monkeypatch.setenv("ECO_SSO_ROLE_MAP", json.dumps({"boss": "指挥长"}))
        assert sso_mod.map_role({"role": "boss"}) is rbac.Role.COMMANDER

    def test_unknown_role_degrades(self):
        assert sso_mod.map_role({"role": "super-root"}) is rbac.Role.READONLY_VISITOR
        assert sso_mod.map_role({}) is rbac.Role.READONLY_VISITOR

    def test_mapped_role_rbac_check(self, monkeypatch):
        monkeypatch.setenv("ECO_SSO_ROLE_MAP", json.dumps({"audit": "审计员"}))
        role = sso_mod.map_role({"role": "audit"})
        assert rbac.check(role, rbac.Capability.TRACE_EXPORT)
        assert not rbac.check(role, rbac.Capability.CHANNEL_MANAGE)


# ---------------------------------------------------------------------------
# 会话 token
# ---------------------------------------------------------------------------
@pytest.fixture()
def isolated_secret(tmp_path, monkeypatch):
    monkeypatch.setattr(grants_mod, "SECRET_FILE", tmp_path / "grant_secret")


class TestSession:
    def test_issue_and_verify(self, isolated_secret):
        tok = sso_mod.issue_session({"sub": "u-1", "name": "李四"}, rbac.Role.ENFORCER)
        sess = sso_mod.verify_session(tok)
        assert sess["sub"] == "u-1" and sess["role"] == "执法员"

    def test_ttl_expired(self, isolated_secret):
        tok = sso_mod.issue_session({"sub": "u-1"}, rbac.Role.ADMIN, ttl=-1)
        assert sso_mod.verify_session(tok) is None

    def test_tampered_rejected(self, isolated_secret):
        tok = sso_mod.issue_session({"sub": "u-1"}, rbac.Role.ADMIN)
        payload, sig = tok.rsplit(".", 1)
        forged = _b64(json.dumps({"sub": "u-1", "role": "admin", "expires_at": time.time() + 9999}).encode()) + "." + sig
        assert sso_mod.verify_session(forged) is None
        assert sso_mod.verify_session("garbage") is None


# ---------------------------------------------------------------------------
# gateway 集成
# ---------------------------------------------------------------------------
@pytest.fixture()
def gw(monkeypatch, tmp_path):
    """启动 SSO 开启的渠道网关（http_fn 全 mock）"""
    monkeypatch.setenv("ECO_SSO", "1")
    monkeypatch.setattr(grants_mod, "SECRET_FILE", tmp_path / "grant_secret")
    httpd = http_server.make_server("127.0.0.1", 0)
    import threading

    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    http_server.set_sso_provider(None)


def _get(url, headers=None):
    req = urllib.request.Request(url)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=3) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a):
        return None


def _get_no_redirect(url):
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(url, timeout=3) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


class TestGateway:
    def test_login_302(self, gw, cfg, monkeypatch):
        p = _make_provider(cfg, {f"{ISSUER}/.well-known/openid-configuration": DISCOVERY})
        http_server.set_sso_provider(p)
        status, headers, _ = _get_no_redirect(gw + "/auth/login")
        assert status == 302
        assert headers["Location"].startswith(f"{ISSUER}/authorize?")
        assert "state=" in headers["Location"]

    def test_login_gated_off(self, gw, monkeypatch):
        monkeypatch.delenv("ECO_SSO")
        status, _, _ = _get_no_redirect(gw + "/auth/login")
        assert status == 404

    def test_callback_full_flow(self, gw, cfg, rsa_keys):
        priv, jwk = rsa_keys
        id_token = _jwt(priv, CLAIMS)
        routes = {
            f"{ISSUER}/.well-known/openid-configuration": DISCOVERY,
            f"{ISSUER}/token": {"id_token": id_token},
            f"{ISSUER}/jwks": {"keys": [jwk]},
        }
        p = _make_provider(cfg, routes)
        http_server.set_sso_provider(p)
        _, state = p.authorization_url()
        status, _, body = _get(f"{gw}/auth/callback?code=c1&state={state}")
        assert status == 200
        data = json.loads(body)
        assert data["sub"] == "u-001" and data["role"] == "指挥长"
        assert sso_mod.verify_session(data["session_token"])

    def test_callback_bad_state_401(self, gw, cfg):
        p = _make_provider(cfg, {f"{ISSUER}/.well-known/openid-configuration": DISCOVERY})
        http_server.set_sso_provider(p)
        status, _, body = _get(f"{gw}/auth/callback?code=c1&state=forged")
        assert status == 401 and b"CSRF" in body

    def test_channels_management_requires_session(self, gw):
        status, _, _ = _get(gw + "/channels/feishu")  # GET 无握手参数 → 管理类
        assert status == 401

    def test_channels_management_with_session(self, gw, isolated_channel=None):
        tok = sso_mod.issue_session({"sub": "u-1"}, rbac.Role.ADMIN)
        status, _, _ = _get(gw + "/channels/feishu", {"Authorization": f"Bearer {tok}"})
        assert status != 401  # 通过门控（渠道握手逻辑照常）

    def test_channel_post_callback_exempt(self, gw):
        req = urllib.request.Request(gw + "/channels/feishu", data=b"{}", method="POST")
        try:
            with urllib.request.urlopen(req, timeout=3) as r:
                assert r.status == 200  # 消息回调豁免，不被 SSO 拦 401
        except urllib.error.HTTPError as e:
            assert e.code != 401

    def test_sso_off_no_guard(self, gw, monkeypatch):
        monkeypatch.delenv("ECO_SSO")
        status, _, _ = _get(gw + "/channels/feishu")
        assert status != 401


# ---------------------------------------------------------------------------
# CAS
# ---------------------------------------------------------------------------
CAS_OK = """<?xml version="1.0"?>
<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:authenticationSuccess>
    <cas:user>wangwu</cas:user>
    <cas:attributes>
      <cas:cn>王五</cas:cn>
      <cas:role>audit</cas:role>
    </cas:attributes>
  </cas:authenticationSuccess>
</cas:serviceResponse>"""

CAS_FAIL = """<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:authenticationFailure code="INVALID_TICKET">ticket 无效</cas:authenticationFailure>
</cas:serviceResponse>"""


class TestCAS:
    def test_parse_success(self):
        v = sso_mod.parse_cas_validate_xml(CAS_OK)
        assert v["sub"] == "wangwu" and v["name"] == "王五"
        assert v["attributes"]["role"] == "audit"

    def test_parse_failure(self):
        with pytest.raises(sso_mod.SSOError, match="INVALID_TICKET"):
            sso_mod.parse_cas_validate_xml(CAS_FAIL)

    def test_parse_bad_xml(self):
        with pytest.raises(sso_mod.SSOError):
            sso_mod.parse_cas_validate_xml("not xml")

    def test_cas_validate_http_mock(self):
        calls = []

        def http(req, timeout):
            calls.append(req.full_url)
            return CAS_OK.encode()

        v = sso_mod.cas_validate(
            "ST-1", service="http://gw/auth/callback", validate_url="https://cas.gov/p3/serviceValidate", http_fn=http
        )
        assert v["sub"] == "wangwu"
        assert "ticket=ST-1" in calls[0] and "service=" in calls[0]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
class TestCLI:
    def test_sso_status(self, monkeypatch, capsys):
        monkeypatch.delenv("ECO_SSO", raising=False)
        monkeypatch.delenv("ECO_SSO_ISSUER", raising=False)
        from eco.cli import main

        rc = main(["auth", "sso", "status"])
        out = capsys.readouterr().out
        assert rc == 0 and "enabled=否" in out and "discovery=跳过" in out
