#!/usr/bin/env python3
"""
tool_registry.py — ECO AGENT 自注册工具系统

对标 Hermes Agent 的 registry.register() 自注册工具机制。

每个工具是一个独立文件，通过 @tool 装饰器自动注册。
无需手动配置表，import 即注册。

用法：
  from _scripts.tool_registry import registry

  @registry.register("eco_search", "检索生态环境法规知识库")
  def eco_search(query: str, max_results: int = 10):
      '''检索法规知识库'''
      ...

  # 列出所有工具
  registry.list_tools()
"""

import os
import inspect
import logging
from typing import Any
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("tool_registry")


@dataclass
class ToolEntry:
    """工具条目"""
    name: str
    description: str
    handler: Callable
    parameters: dict[str, Any]
    toolset: str = "eco"
    requires_env: list[str] = field(default_factory=list)
    is_async: bool = False
    risk_level: str = "read"  # read | write | exec | external
    timeout: int = 30


class ToolRegistry:
    """工具注册表（单例）"""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._tools: dict[str, ToolEntry] = {}
            cls._instance._toolsets: dict[str, list[str]] = {}
            cls._instance._discover_done = False
        return cls._instance

    def register(self, name: str = None, description: str = "",
                 toolset: str = "eco", risk_level: str = "read",
                 requires_env: list[str] = None) -> Callable:
        """装饰器：注册工具"""
        def decorator(func: Callable) -> Callable:
            tool_name = name or func.__name__
            sig = inspect.signature(func)
            params = {
                p_name: {
                    "type": str(p.annotation.__name__ if p.annotation != inspect.Parameter.empty else "string"),
                    "default": p.default if p.default != inspect.Parameter.empty else None,
                    "required": p.default == inspect.Parameter.empty,
                }
                for p_name, p in sig.parameters.items()
                if p_name not in ("self", "cls")
            }

            self._tools[tool_name] = ToolEntry(
                name=tool_name,
                description=description or func.__doc__ or "",
                handler=func,
                parameters=params,
                toolset=toolset,
                requires_env=requires_env or [],
                is_async=inspect.iscoroutinefunction(func),
                risk_level=risk_level,
            )

            if toolset not in self._toolsets:
                self._toolsets[toolset] = []
            self._toolsets[toolset].append(tool_name)

            logger.debug(f"[Registry] 注册工具: {tool_name} ({toolset})")
            return func
        return decorator

    def get(self, name: str) -> ToolEntry | None:
        return self._tools.get(name)

    def list_tools(self, toolset: str = None) -> list[ToolEntry]:
        if toolset:
            return [self._tools[n] for n in self._toolsets.get(toolset, []) if n in self._tools]
        return list(self._tools.values())

    def get_openai_schemas(self, toolset: str = None) -> list[dict]:
        """输出 OpenAI Function Calling 格式的 schemas"""
        schemas = []
        for tool in self.list_tools(toolset):
            props = {}
            required = []
            for p_name, p_info in tool.parameters.items():
                if p_info["required"]:
                    required.append(p_name)
                props[p_name] = {
                    "type": p_info["type"],
                    "description": f"参数 {p_name}",
                }
                if p_info["default"] is not None:
                    props[p_name]["default"] = p_info["default"]

            schemas.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": {
                        "type": "object",
                        "properties": props,
                        "required": required,
                    },
                },
            })
        return schemas

    def call(self, name: str, **kwargs) -> Any:
        """调用工具"""
        tool = self.get(name)
        if not tool:
            raise KeyError(f"工具不存在: {name}")

        # 检查环境变量
        for env_key in tool.requires_env:
            if not os.environ.get(env_key):
                raise OSError(f"缺少环境变量: {env_key}")

        logger.info(f"[Registry] 调用工具: {name} kwargs={kwargs}")
        return tool.handler(**kwargs)

    def discover_scripts(self, scripts_dir: str = None):
        """自动发现并注册 _scripts/ 目录下的工具"""
        if self._discover_done:
            return
        self._discover_done = True

        if not scripts_dir:
            scripts_dir = str(Path(__file__).resolve().parent)
        scripts_path = Path(scripts_dir)

        # 跳过独立运行脚本（有 main 调用且不是工具类脚本）
        SKIP_PATTERNS = ["watch_loop", "daemon_loop", "while True"]

        for py_file in sorted(scripts_path.glob("*.py")):
            if py_file.name.startswith("_") or py_file.name == os.path.basename(__file__):
                continue
            try:
                content = py_file.read_text("utf-8", errors="replace")
                # 跳过独立守护类脚本
                if any(p in content for p in SKIP_PATTERNS) and "def " not in content[:500]:
                    continue
                spec = importlib.util.spec_from_file_location(
                    py_file.stem, str(py_file))
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                logger.info(f"[Registry] 发现脚本: {py_file.name}")
            except Exception as e:
                logger.warning(f"[Registry] 加载失败 {py_file.name}: {e}")


# 全局单例
registry = ToolRegistry()


# ===== 内置工具 =====

@registry.register("echo", "回显输入")
def echo(text: str = "hello") -> str:
    return text

@registry.register("list_tools", "列出所有已注册工具")
def list_tools(toolset: str = "") -> str:
    tools = registry.list_tools(toolset) if toolset else registry.list_tools()
    if not tools:
        return "暂无已注册工具"
    lines = ["已注册工具："]
    for t in tools:
        lines.append(f"  - {t.name}: {t.description[:40]} ({t.toolset}/{t.risk_level})")
    return "\n".join(lines)


# ===== 测试 =====

def test():
    registry.discover_scripts()
    tools = registry.list_tools()
    print(f"[TEST] 已注册 {len(tools)} 个工具")
    for t in tools[:10]:
        print(f"  - {t.name}: {t.description[:30]}")

    schemas = registry.get_openai_schemas()
    print(f"\n[TEST] OpenAI Schemas: {len(schemas)} 个")

    result = registry.call("echo", text="ECO AGENT")
    print(f"[TEST] echo 调用: {result}")

    print("\n[OK] 自注册工具系统测试通过")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import importlib.util
    test()
