# ECO AGENT 插件系统

> 目录规范：`plugins/<name>/plugin.yaml` + `plugins/<name>/handler.py`
> 加载器：`agent_core/plugins.py`（PluginManager，热加载/卸载/重载）
> 安全模型：工具经 L1-L4 风险闸门（`agent_core/permissions.py`），未知工具默认 L3

## 目录结构

```
plugins/
└── <plugin-name>/
    ├── plugin.yaml      # 元数据（必填 name）
    └── handler.py       # 生命周期入口：def load(ctx) / def unload(ctx)
```

## plugin.yaml 格式

```yaml
name: example            # 必填，目录名一致
version: 0.1.0
description: 示例插件
entry: handler           # 入口模块名（默认 handler）
tools:                   # 声明注册的工具（与 handler 注册一致）
  - name: example_echo
    description: 回显工具
    risk_level: L1       # L1 READ / L2 WRITE_LOCAL / L3 EXEC / L4 EXTERNAL
permissions:             # 工具风险级覆盖（可选，精确声明）
  example_echo: L1
```

## handler.py 生命周期

```python
def load(ctx):
    """加载时执行：注册工具。返回 dict（会记录到加载结果）。"""
    ctx.register_tool("example_echo", echo, description="回显", risk_level="L1")
    ctx.log("loaded")
    return {"ok": True}


def unload(ctx):
    """卸载时执行：清理副作用。"""
    ctx.log("unloaded")
    return {"ok": True}


def echo(text: str) -> str:
    return text
```

## PluginContext API

| 方法 | 说明 |
|---|---|
| `ctx.register_tool(name, handler, description=..., risk_level=...)` | 注册工具（L1-L4 风险级） |
| `ctx.log(message)` | 写插件日志 |
| `ctx.plugin_name` / `ctx.metadata` | 插件身份与已注册工具元数据 |

## 安全规则

1. 未知工具默认 **L3**（保守），`plugin.yaml` 可用 `permissions` 精确声明。
2. 工具名跨插件唯一：冲突时 `load(force=False)` 拒绝加载。
3. 调用走 `PluginManager.call_tool()`，经 `gate_tool_call` L1-L4 闸门。

## API / CLI

```bash
# 管理 API（eco-server）
GET  /api/v1/plugins                 # 列表
POST /api/v1/plugins/{name}/load     # 热加载
POST /api/v1/plugins/{name}/unload   # 卸载
POST /api/v1/plugins/{name}/reload   # 重载
POST /api/v1/plugins/call            # 调用插件工具（经权限闸门）
```
