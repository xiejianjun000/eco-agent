"""国内通讯渠道网关 — 抽象基类与统一消息模型（模块 B）

所有渠道适配器实现 Channel 接口：
- verify(request)  验签 / token 校验
- parse(request)   平台回调 → InboundMessage
- reply(user_id, text)  调平台 API 主动发消息（子类覆盖）

内置安全：parse 出的 text 必须经 agent_core.prompt_engine.validate_injection
检查，拦截时回复固定话术 BLOCK_TEXT 且不进入 chat 管道。
"""
from __future__ import annotations

import json
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import ClassVar, Optional

from agent_core.prompt_engine import validate_injection

#: 注入拦截固定话术（契约，不得更改）
BLOCK_TEXT = "[安全拦截] 消息未通过安全检查"
#: 验签失败固定话术
VERIFY_FAIL_TEXT = "[验签失败] 请求签名校验未通过"


@dataclass
class InboundMessage:
    channel: str          # "wecom" 等
    user_id: str
    text: str
    msg_id: str = ""
    extras: dict = field(default_factory=dict)


class Channel(ABC):
    """渠道适配器抽象基类。"""

    name: ClassVar[str] = ""
    #: 子类声明所需配置的环境变量名（仅文档/展示用途）
    env_keys: ClassVar[tuple[str, ...]] = ()

    def __init__(self, config: Optional[dict] = None):
        # 配置一律来自环境变量占位符或显式 dict（测试注入），仓库内禁止真实 secret
        self.config = dict(config or {})

    @abstractmethod
    def verify(self, request: dict) -> bool:
        """验签 / token 校验。request 为 gateway HTTP 层规整后的 dict：
        {"method", "headers", "args"(query), "body"(bytes|str), "json"(已解析 body)}
        """

    @abstractmethod
    def parse(self, request: dict) -> Optional[InboundMessage]:
        """解析平台回调为统一消息；无法解析返回 None。"""

    def reply(self, user_id: str, text: str, **kw) -> bool:
        """主动发消息（调平台 API）。默认未实现，子类覆盖。"""
        raise NotImplementedError(f"{self.name} 未实现 reply")

    # ---- 内置安全管道 ----
    def check_injection(self, msg: InboundMessage) -> bool:
        """True=放行；False=注入拦截。"""
        ok, _reason = validate_injection(msg.text)
        return ok

    def safe_parse(self, request: dict) -> tuple[Optional[InboundMessage], Optional[str]]:
        """parse + 注入检查。返回 (msg, None) / (msg, BLOCK_TEXT) / (None, None)。"""
        msg = self.parse(request)
        if msg is None:
            return None, None
        if not self.check_injection(msg):
            return msg, BLOCK_TEXT
        return msg, None


def http_post_json(url: str, payload: dict, headers: Optional[dict] = None,
                   timeout: int = 10) -> dict:
    """POST JSON（urllib 实现；测试中 mock 此函数，禁止真实外呼）。"""
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json; charset=utf-8")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8"))


def body_bytes(request: dict) -> bytes:
    """统一取原始请求体 bytes。"""
    body = request.get("body", b"")
    if isinstance(body, str):
        return body.encode("utf-8")
    return body or b""


def body_json(request: dict) -> dict:
    """取已解析 JSON 体；没有则尝试解析 body。"""
    j = request.get("json")
    if isinstance(j, dict):
        return j
    raw = body_bytes(request)
    if not raw:
        return {}
    try:
        return json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return {}
