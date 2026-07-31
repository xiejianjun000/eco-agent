"""渠道统一 HTTP 入站服务（标准库 http.server 实现，零新增依赖）。

路由：
  GET  /healthz             健康检查 → 200 {"status": "ok"}
  POST /channels/<name>     渠道回调 → registry.handle_inbound(name, request)
                            → 200 {"reply": ...}（验签失败按 registry 语义仍回 200
                              固定话术，平台要求回调失败不得返回 4xx/5xx）
  GET  /channels/<name>     URL 验证握手：
                              - feishu    → {"challenge": ...} JSON
                              - wecom/wechat_oa → 解密后的 echostr 纯文本
  未知渠道名 / 未知路径     → 404

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

    def _route(self, method: str) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        args = dict(parse_qsl(parsed.query))

        if method == "GET" and path == "/healthz":
            payload = json.dumps({"status": "ok"}).encode("utf-8")
            self._send(200, _JSON, payload)
            return

        parts = [p for p in path.split("/") if p]
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

    def do_GET(self) -> None:  # noqa: N802（stdlib 约定）
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
