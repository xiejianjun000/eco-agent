---
id: github-mcp-server
name: GitHub MCP Server (Official)
version: 2.0.0
description: |
  GitHub官方MCP服务器。支持OAuth/PAT认证，提供PR、Issue、Actions、仓库管理、代码搜索等完整GitHub API能力。
  32,422 stars, 维护等级A。
category: MCP生态
triggers:
  - github操作
  - 仓库管理
  - PR审查
  - issue跟踪
  - github mcp
parameters:
  auth:
    type: string
    description: OAuth或PAT认证令牌
    required: true
  toolset:
    type: string
    description: 工具集配置
    required: false
    default: default
author: GitHub (official)
source: https://github.com/github/github-mcp-server
license: MIT
status: active
---

# GitHub MCP Server

## 安装
```bash
# 远程MCP（零安装）
# 配置OAuth或PAT即可使用
```

## 能力
- 仓库管理：创建/删除/搜索仓库
- PR操作：创建/合并/审查/评论
- Issue管理：创建/关闭/标签/分配
- Actions：查看日志/重试工作流
- 代码搜索：跨仓库符号搜索
- 安全审计：39个工具，45项检查
