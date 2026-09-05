#!/usr/bin/env python3
"""
govmcp.tools.registry — 工具注册中心
====================================

提供 ToolRegistry 类用于管理工具注册/注销/列表/调用，
以及 govmcp_tool 装饰器用于便捷地将 Python 函数注册为 MCP 工具。

标准 MCP 输出格式:
- tools/list: {"tools": [{"name": "...", "description": "...", "inputSchema": {...}}]}
- tools/call: {"content": [{"type": "text", "text": "..."}], "isError": false}
"""

from __future__ import annotations

import functools
import inspect
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Optional, get_type_hints

# ---------------------------------------------------------------------------
# JSON Schema 类型推断
# ---------------------------------------------------------------------------

_TYPE_MAP: dict[type, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
    type(None): "null",
}


def _python_type_to_json_schema(py_type: type) -> dict[str, Any]:
    """将 Python 类型映射为 JSON Schema type 片段。"""
    origin = getattr(py_type, "__origin__", None)
    if origin is not None:
        # typing.Optional[X] → 可能是不带 None 的
        args = getattr(py_type, "__args__", ())
        if origin is list:
            item_schema = _python_type_to_json_schema(args[0]) if args else {}
            return {"type": "array", "items": item_schema}
        if origin is dict:
            return {"type": "object"}
        if origin is Optional or origin is type(None).__class__:
            # Optional[X] = Union[X, None]
            non_none = [a for a in args if a is not type(None)]
            if len(non_none) == 1:
                return _python_type_to_json_schema(non_none[0])
            return {"type": "string"}

    base = _TYPE_MAP.get(py_type)
    if base:
        return {"type": base}
    return {"type": "string"}  # fallback


def _infer_input_schema(func: Callable) -> dict[str, Any]:
    """
    从函数签名自动推断 JSON Schema input schema。

    会跳过 *args, **kwargs 以及名为 'self'/'cls' 的参数。
    """
    sig = inspect.signature(func)
    hints = {}
    try:
        hints = get_type_hints(func)
    except Exception:
        pass

    properties: dict[str, dict[str, Any]] = {}
    required: list[str] = []

    for name, param in sig.parameters.items():
        # 跳过 self / cls
        if name in ("self", "cls"):
            continue
        # 跳过 *args / **kwargs
        if param.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue

        py_type = hints.get(name, str)
        schema_fragment = _python_type_to_json_schema(py_type)

        # 检查是否有默认值 → 不是 required
        if param.default is inspect.Parameter.empty:
            required.append(name)
        else:
            schema_fragment["default"] = param.default

        # 如果有 docstring 标注参数说明 → 提取（简单策略：取第一段）
        # 这里不做过度解析，保持简洁
        properties[name] = schema_fragment

    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
    }
    if required:
        schema["required"] = required

    return schema


# ---------------------------------------------------------------------------
# ToolInfo 数据类
# ---------------------------------------------------------------------------


@dataclass
class ToolInfo:
    """MCP 工具的描述信息。"""

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable
    approval_required: bool = False
    audit_enabled: bool = True

    def to_mcp_dict(self) -> dict[str, Any]:
        """转为标准 MCP tools/list 条目。"""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """工具对象可直接调用，转发到注册的 handler。"""
        return self.handler(*args, **kwargs)


# ---------------------------------------------------------------------------
# ToolRegistry — 工具注册中心
# ---------------------------------------------------------------------------


class ToolRegistry:
    """
    MCP 工具注册中心。

    管理所有已注册的工具，提供注册/注销/查询/列表/调用能力。

    用法:
        registry = ToolRegistry()
        registry.register("add", "Add two numbers", schema, handler)
        result = registry.call_tool("add", {"a": 1, "b": 2})
    """

    def __init__(self) -> None:
        self.tools: dict[str, ToolInfo] = {}

    # ---- 注册 / 注销 --------------------------------------------------

    def register(
        self,
        name: str | Callable,
        description: str = "",
        input_schema: dict[str, Any] | None = None,
        handler: Callable | None = None,
        approval_required: bool = False,
        audit_enabled: bool = True,
    ) -> None:
        """
        注册一个工具。

        两种调用形式：
        1. 显式注册：register(name, description, input_schema, handler, ...)
        2. 装饰器注册：register(decorated_func)——func 携带 _govmcp_meta 元信息

        Args:
            name: 工具名称（唯一标识），或已用 @govmcp_tool 装饰的函数。
            description: 工具描述。
            input_schema: JSON Schema 格式的输入参数定义。
            handler: 工具调用时执行的函数。
            approval_required: 是否需要审批。
            audit_enabled: 是否启用审计。
        """
        # 装饰器形式：register(func)
        if callable(name) and hasattr(name, "_govmcp_meta"):
            meta = name._govmcp_meta  # type: ignore[attr-defined]
            self._register_tool(
                name=meta["name"],
                description=meta.get("description", ""),
                input_schema=meta.get("input_schema", {}),
                handler=name,
                approval_required=meta.get("approval_required", False),
                audit_enabled=meta.get("audit_enabled", True),
            )
            return
        if not isinstance(name, str) or handler is None:
            raise ValueError("register() requires either a decorated function or (name, description, input_schema, handler)")
        self._register_tool(
            name=name,
            description=description,
            input_schema=input_schema or {},
            handler=handler,
            approval_required=approval_required,
            audit_enabled=audit_enabled,
        )

    def register_batch(self, funcs: list[Callable]) -> int:
        """批量注册携带 _govmcp_meta 的装饰函数，返回成功注册数量。"""
        count = 0
        for func in funcs:
            if callable(func) and hasattr(func, "_govmcp_meta"):
                self.register(func)
                count += 1
        return count

    def _register_tool(
        self,
        name: str,
        description: str,
        input_schema: dict[str, Any],
        handler: Callable,
        approval_required: bool = False,
        audit_enabled: bool = True,
    ) -> None:
        if not name or not isinstance(name, str):
            raise ValueError("Tool name must be a non-empty string.")
        if name in self.tools:
            raise ValueError(f"Tool '{name}' is already registered.")

        self.tools[name] = ToolInfo(
            name=name,
            description=description,
            input_schema=input_schema,
            handler=handler,
            approval_required=approval_required,
            audit_enabled=audit_enabled,
        )

    def unregister(self, name: str) -> None:
        """
        注销一个工具。

        Args:
            name: 工具名称。

        Raises:
            KeyError: 工具不存在。
        """
        if name not in self.tools:
            raise KeyError(f"Tool '{name}' is not registered.")
        del self.tools[name]

    # ---- 查询 ---------------------------------------------------------

    def get(self, name: str) -> ToolInfo:
        """
        获取工具信息。

        Args:
            name: 工具名称。

        Returns:
            ToolInfo 对象。

        Raises:
            KeyError: 工具不存在。
        """
        if name not in self.tools:
            raise KeyError(f"Tool '{name}' is not registered.")
        return self.tools[name]

    def count(self) -> int:
        """返回已注册工具数量。"""
        return len(self.tools)

    # ---- MCP 标准输出 -------------------------------------------------

    def list_tools(self) -> list[dict[str, Any]]:
        """
        列出所有工具（标准 MCP tools/list 格式）。

        Returns:
            [{"name": "...", "description": "...", "inputSchema": {...}}, ...]
        """
        return [tool.to_mcp_dict() for tool in self.tools.values()]

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """
        执行工具并返回标准 MCP tools/call 格式。

        Args:
            name: 工具名称。
            arguments: 工具参数字典。

        Returns:
            {
                "content": [{"type": "text", "text": "..."}],
                "isError": false
            }

        Raises:
            KeyError: 工具不存在。
        """
        tool = self.get(name)

        try:
            result = tool.handler(**arguments)
        except Exception as exc:
            return {
                "content": [{"type": "text", "text": str(exc)}],
                "isError": True,
            }

        # 格式化结果为 text
        if isinstance(result, str):
            text = result
        else:
            try:
                text = json.dumps(result, ensure_ascii=False, default=str)
            except (TypeError, ValueError):
                text = str(result)

        return {
            "content": [{"type": "text", "text": text}],
            "isError": False,
        }


# ---------------------------------------------------------------------------
# govmcp_tool 装饰器
# ---------------------------------------------------------------------------


def govmcp_tool(
    name: str | None = None,
    description: str = "",
    approval_required: bool = False,
    audit_enabled: bool = True,
    category: str = "",
    tags: list[str] | None = None,
) -> Callable:
    """
    装饰器：将 Python 函数自动注册为 MCP 工具。

    自动从函数签名 + 类型注解推断 input_schema (JSON Schema)。

    用法:
        @govmcp_tool(description="计算两数之和")
        def add(a: int, b: int) -> int:
            return a + b

        # 装饰后会附加一个 ._govmcp_meta 属性，包含 ToolRegistry.register() 所需信息。
        # 也可配合 ToolRegistry.register_decorated() 批量注册。
        # category/tags 为可选的分类元数据（供工具目录分组展示，不影响注册）。
    """

    def decorator(func: Callable) -> Callable:
        tool_name = name or func.__name__
        tool_description = description or (func.__doc__ or "").strip().split("\n")[0]
        input_schema = _infer_input_schema(func)

        # 将元信息附加到函数对象上
        func._govmcp_meta = {  # type: ignore[attr-defined]
            "name": tool_name,
            "description": tool_description,
            "input_schema": input_schema,
            "approval_required": approval_required,
            "audit_enabled": audit_enabled,
            "category": category,
            "tags": tags or [],
        }

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return func(*args, **kwargs)

        # 将 meta 也复制到 wrapper 上
        wrapper._govmcp_meta = func._govmcp_meta  # type: ignore[attr-defined]
        return wrapper

    return decorator
