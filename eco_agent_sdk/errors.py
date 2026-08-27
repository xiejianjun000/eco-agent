#!/usr/bin/env python3
"""
eco_agent_sdk/errors.py — SDK 错误类型
"""

from __future__ import annotations


class EcoError(Exception):
    """SDK 基础错误。"""


class EcoConnectionError(EcoError):
    """无法连接 eco-server（服务未启动 / 地址错误 / 网络不通）。"""


class EcoApiError(EcoError):
    """eco-server 返回错误状态码。

    Attributes:
        status_code: HTTP 状态码
        detail: 服务端错误信息
    """

    def __init__(self, status_code: int, detail: str = "") -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"eco-server API error {status_code}: {detail or 'no detail'}")
