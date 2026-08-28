"""渠道统一 HTTP 入站服务（标准库 http.server 实现，零新增依赖）。

路由：
  GET  /healthz             健康检查 → 200 {"status": "ok"}
  POST /channels/<name>     渠道回调 → registry.handle_inbound(name, request)
                            → 200 {"reply": ...}（验签失败按 registry 语义仍回 200
                              固定话术，平台要求回调失败不得返回 4xx/5xx）
  GET  /channels/<name>     URL 验证握手：
                              - feishu    → {"challenge": ...} JSON
                              - wecom/wechat_oa → 解密后的 echostr 纯文本
  GET  /auth/login          SSO 登录入口（ECO_SSO=1 时 302 到 IdP 授权 URL）
  GET  /auth/callback       SSO 回调（code/ticket → 本地会话 token JSON）
  未知渠道名 / 未知路径     → 404

SSO 门控（ECO_SSO=1，agent_core.sso）：/channels/* 的管理类请求
（非平台消息回调：即 GET 且无握手参数）须携带
`Authorization: Bearer <会话 token>`；平台消息回调（POST 回调、
GET echostr/challenge 握手）豁免——平台服务器无会话。

dispatch_request() 为与传输层无关的分发核心，FastAPI 版
gateway/eco-gateway-server.py 与本 stdlib 服务共用同一逻辑。
"""
from __future__ import annotations

import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qsl, urlparse

from agent_core.channels import registry
from agent_core.channels.registry import CHANNELS

log = logging.getLogger("eco.channels.http")

# SSO 提供方（懒加载单例；测试可经 set_sso_provider 注入 mock）
_SSO_PROVIDER = None


def _sso_provider():
    global _SSO_PROVIDER
    if _SSO_PROVIDER is None:
        from agent_core import sso as sso_mod
        _SSO_PROVIDER = sso_mod.OIDCProvider(sso_mod.OIDCConfig.from_env())
    return _SSO_PROVIDER


def set_sso_provider(provider) -> None:
    """测试/集成注入 SSO 提供方（None 恢复懒加载）。"""
    global _SSO_PROVIDER
    _SSO_PROVIDER = provider


# 平台握手 query 参数（出现即视为消息回调，豁免会话检查）
_HANDSHAKE_KEYS = ("echostr", "challenge", "signature",
                   "msg_signature", "timestamp", "nonce")


def _is_channel_callback(method: str, args: dict) -> bool:
    """平台消息回调判定：POST 回调，或带握手参数的 GET 握手。"""
    if method.upper() == "POST":
        return True
    return any(k in args for k in _HANDSHAKE_KEYS)


def _sso_session_from_headers(headers: dict | None):
    """从 Authorization: Bearer <token> 提取并校验本地会话。"""
    from agent_core import sso as sso_mod
    auth = (headers or {}).get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    return sso_mod.verify_session(auth[len("Bearer "):].strip())

_JSON = "application/json; charset=utf-8"
_TEXT = "text/plain; charset=utf-8"


def _normalize_headers(headers: dict) -> dict:
    """合并大小写变体：渠道验签按原始名（如 X-Signature）取 header，
    FastAPI/httpx 会小写化，这里补一份 Title-Case 别名。"""
    out = dict(headers)
    for k, v in list(out.items()):
        canonical = "-".join(p.capitalize() for p in k.split("-"))
        out.setdefault(canonical, v)
    return out


def dispatch_request(method: str, name: str, headers: dict | None = None,
                     args: dict | None = None, body: bytes = b"",
                     config: dict | None = None) -> tuple[int, str, bytes]:
    """渠道 HTTP 入站分发核心。返回 (status, content_type, body_bytes)。

    验签失败/注入拦截由 handle_inbound 返回固定话术，HTTP 层一律 200
    （企业微信/飞书等平台要求回调应答 2xx，否则反复重推）。
    """
    if name not in CHANNELS:
        payload = {"error": f"未知渠道: {name}",
                   "available": sorted(CHANNELS)}
        return 404, _JSON, json.dumps(payload, ensure_ascii=False).encode("utf-8")

    request = {
        "method": method.upper(),
        "headers": _normalize_headers(headers or {}),
        "args": dict(args or {}),
        "body": body or b"",
    }
    result = registry.handle_inbound(name, request, config)

    # 飞书 url_verification：handle_inbound 返回 {"challenge": ...} JSON 字符串
    try:
        parsed = json.loads(result) if result else None
    except (ValueError, TypeError):
        parsed = None
    if isinstance(parsed, dict) and "challenge" in parsed:
        return 200, _JSON, json.dumps(parsed, ensure_ascii=False).encode("utf-8")

    if method.upper() == "GET":
        # wecom / wechat_oa echostr 握手：平台要求原样回纯文本
        return 200, _TEXT, (result or "").encode("utf-8")
    return 200, _JSON, json.dumps({"reply": result},
                                  ensure_ascii=False).encode("utf-8")


class ChannelRequestHandler(BaseHTTPRequestHandler):
    """stdlib 渠道网关请求处理器。"""

    server_version = "eco-channels/1.0"

    # 测试可注入渠道配置（{channel_name: config_dict}）
    channel_configs: dict = {}

    def _send(self, status: int, content_type: str, payload: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _redirect(self, location: str) -> None:
        self.send_response(302)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    # ------------------------------------------------------------------
    # SSO 路由与门控（ECO_SSO=1 才生效，agent_core.sso）
    # ------------------------------------------------------------------
    def _sso_login(self) -> None:
        from agent_core import sso as sso_mod
        if not sso_mod.sso_enabled():
            self._send(404, _JSON, json.dumps(
                {"error": "SSO 未启用（ECO_SSO）"}, ensure_ascii=False).encode("utf-8"))
            return
        try:
            cfg = _sso_provider().config
            if cfg.protocol == "cas":
                url = self._cas_login_url(cfg, cfg.redirect_uri or "")
            else:
                url, _state = _sso_provider().authorization_url()
        except Exception as e:
            self._send(502, _JSON, json.dumps(
                {"error": f"SSO discovery 失败: {e}"},
                ensure_ascii=False).encode("utf-8"))
            return
        self._redirect(url)

    @staticmethod
    def _cas_login_url(cfg, service: str) -> str:
        from urllib.parse import urlencode
        base = cfg.issuer.rstrip("/") + "/login"
        return f"{base}?{urlencode({'service': service})}" if service else base

    def _sso_callback(self, args: dict) -> None:
        from agent_core import sso as sso_mod
        if not sso_mod.sso_enabled():
            self._send(404, _JSON, json.dumps(
                {"error": "SSO 未启用（ECO_SSO）"}, ensure_ascii=False).encode("utf-8"))
            return
        provider = _sso_provider()
        cfg = provider.config
        try:
            if cfg.protocol == "cas":
                identity = self._cas_identity(provider, args)
            else:
                identity = self._oidc_identity(provider, args)
        except sso_mod.SSOError as e:
            self._send(401, _JSON, json.dumps(
                {"error": str(e)}, ensure_ascii=False).encode("utf-8"))
            return
        role = sso_mod.map_role(
            {cfg.role_claim: identity.get("role_claim", "")}, cfg.role_claim) \
            if identity.get("role_claim") else sso_mod.rbac.Role.READONLY_VISITOR
        token = sso_mod.issue_session(identity, role, ttl=cfg.session_ttl)
        payload = json.dumps({
            "session_token": token, "sub": identity.get("sub", ""),
            "name": identity.get("name", ""), "role": role.value,
            "expires_in": cfg.session_ttl,
        }, ensure_ascii=False).encode("utf-8")
        self._send(200, _JSON, payload)

    @staticmethod
    def _oidc_identity(provider, args: dict) -> dict:
        from agent_core import sso as sso_mod
        code, state = args.get("code", ""), args.get("state", "")
        if not code:
            raise sso_mod.SSOError("回调缺少 code")
        if not provider.check_state(state):
            raise sso_mod.SSOError("state 校验失败（疑似 CSRF）")
        tok = provider.exchange_code(code)
        claims = provider.verify_id_token(tok["id_token"])
        return provider.extract_claims(claims)

    @staticmethod
    def _cas_identity(provider, args: dict) -> dict:
        from agent_core import sso as sso_mod
        ticket = args.get("ticket", "")
        if not ticket:
            raise sso_mod.SSOError("回调缺少 ticket")
        v = sso_mod.cas_validate(ticket, service=provider.config.redirect_uri,
                                 validate_url=provider.config.cas_validate_url,
                                 http_fn=provider._http)
        role = v.get("attributes", {}).get(provider.config.role_claim, "")
        return {"sub": v["sub"], "name": v.get("name", ""), "role_claim": role}

    def _sso_guard_channels(self, method: str, args: dict) -> bool:
        """ECO_SSO=1 时，/channels/* 管理类请求要求有效会话；
        平台消息回调豁免。返回 True 表示已拦截（401）。"""
        from agent_core import sso as sso_mod
        if not sso_mod.sso_enabled():
            return False
        if _is_channel_callback(method, args):
            return False
        if _sso_session_from_headers(dict(self.headers.items())) is not None:
            return False
        self._send(401, _JSON, json.dumps(
            {"error": "需要有效 SSO 会话（Authorization: Bearer <token>）"},
            ensure_ascii=False).encode("utf-8"))
        return True

    def _route(self, method: str) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        args = dict(parse_qsl(parsed.query))

        if method == "GET" and path == "/healthz":
            payload = json.dumps({"status": "ok"}).encode("utf-8")
            self._send(200, _JSON, payload)
            return

        if method == "GET" and path == "/auth/login":
            self._sso_login()
            return
        if method == "GET" and path == "/auth/callback":
            self._sso_callback(args)
            return

        parts = [p for p in path.split("/") if p]
        if parts and parts[0] == "channels" \
                and not _is_channel_callback(method, args) \
                and self._sso_guard_channels(method, args):
            return
        if len(parts) == 2 and parts[0] == "channels":
            body = b""
            if method == "POST":
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length) if length > 0 else b""
            name = parts[1]
            status, ctype, payload = dispatch_request(
                method, name, headers=dict(self.headers.items()),
                args=args, body=body,
                config=self.channel_configs.get(name))
            self._send(status, ctype, payload)
            return

        self._send(404, _JSON, json.dumps(
            {"error": f"未知路径: {method} {path}"},
            ensure_ascii=False).encode("utf-8"))

    def do_GET(self) -> None:  # noqa: N802 (stdlib 约定)
        self._route("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._route("POST")

    def log_message(self, fmt, *a):  # 交给 logging，避免写 stderr
        log.debug("%s - %s", self.address_string(), fmt % a)


def make_server(host: str = "0.0.0.0", port: int = 7080,
                channel_configs: dict | None = None) -> ThreadingHTTPServer:
    """构建渠道网关 HTTP 服务（port=0 时由系统分配，测试用）。"""
    handler = type("Handler", (ChannelRequestHandler,), {})
    handler.channel_configs = dict(channel_configs or {})
    return ThreadingHTTPServer((host, port), handler)


def serve(host: str = "0.0.0.0", port: int = 7080) -> None:  # pragma: no cover
    srv = make_server(host, port)
    log.info("[channels] 渠道入站服务: http://%s:%d/channels/<name>", host, port)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":  # pragma: no cover
    import sys
    logging.basicConfig(level=logging.INFO)
    serve(port=int(sys.argv[1]) if len(sys.argv) > 1 else 7080)
