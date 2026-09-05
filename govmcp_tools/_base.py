#!/usr/bin/env python3
"""
govmcp_tools._base — 政务平台工具集公共设施
================================================
P2-2 govmcp 真实化（对标 Hermes 生态纵深）：
- 工具 handler 统一异常降级：只读语义，失败返回 error 字段，绝不返回虚构数据
- SM3 审计链尽力而为（govmcp.crypto.audit 缺失时跳过，不影响业务）
- CHAT_TOOLS 规范：name/description/parameters/handler 四要素
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable

logger = logging.getLogger("govmcp_tools")


def safe_handler(fn: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
    """包装真实数据源 handler：异常统一转为 error 结果（不抛栈、不造假）。"""

    def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
        t0 = time.monotonic()
        try:
            result = fn(*args, **kwargs)
            if isinstance(result, dict) and "error" in result:
                return result
            return result
        except Exception as exc:  # noqa: BLE001 — 只读工具异常降级为可读 error
            logger.debug("[govmcp_tools] %s 调用失败: %s", getattr(fn, "__name__", "?"), exc)
            return {"error": f"数据获取失败: {exc}", "source": "govmcp_tools"}
        finally:
            _audit(getattr(fn, "__name__", "govmcp_tool"), args, kwargs, int((time.monotonic() - t0) * 1000))

    wrapper.__name__ = getattr(fn, "__name__", "wrapper")
    wrapper.__doc__ = getattr(fn, "__doc__", "")
    return wrapper


def _audit(tool: str, args: tuple, kwargs: dict, duration_ms: int) -> None:
    """SM3 审计链（尽力而为）：协议层 govmcp.crypto 可用时落链，否则跳过。"""
    try:
        from govmcp.crypto.audit import AuditChain

        payload = json.dumps({"args": list(args)[1:] if args else [], "kwargs": kwargs}, ensure_ascii=False).encode("utf-8")
        chain = AuditChain()
        chain.add_entry(
            operation=f"tool_call:{tool}",
            operator="govmcp_tools",
            input_data=payload[:500],
            output_data=b"",
            approval_status="approved",
        )
    except Exception:  # noqa: BLE001 — 审计不可用不阻断业务
        pass


def tool_spec(
    name: str, description: str, parameters: dict[str, Any], handler: Callable[..., dict[str, Any]]
) -> dict[str, Any]:
    """构造 CHAT_TOOLS 单工具条目。"""
    return {
        "name": name,
        "description": description,
        "parameters": parameters,
        "handler": safe_handler(handler),
    }
