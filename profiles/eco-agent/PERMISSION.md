# PERMISSION.md — ECO AGENT 工具权限配置

> **基于 OpenWorker Risk Model 的 4 级风险权限体系**
> 版本：v0.1.0

---

## 风险等级定义

| 等级 | 标签 | 定义 | 审批要求 |
|:----:|:-----|:-----|:---------|
| **L1** | READ | 只读操作，无副作用 | 自动允许 |
| **L2** | WRITE_LOCAL | 在安全区域内创建/修改文件 | 自动允许 |
| **L3** | EXEC | 执行命令/脚本 | 路径白名单内自动允许，其余审批 |
| **L4** | EXTERNAL | 网络请求/外部服务调用 | 必须人工审批 |

---

## 工具权限清单

### L1 — READ（只读）

```yaml
allow:
  - path: "~/.eco/profiles/eco-agent/**"
    reason: "Profile 目录内的配置读取"
  - path: "~/.eco/workspace/**"
    reason: "项目文件读取"
  - path: "~/Documents/Obsidian Vault/raw/**"
    reason: "知识原文只读检索"
  - path: "~/Documents/Obsidian Vault/wiki/**"
    reason: "知识知识只读检索"
  - mcp_tools:
      - eco-knowledge/search
      - eco-knowledge/retrieve
      - obsidian-vault/search
      - obsidian-vault/read
  - web_search: true
  - web_fetch: true
```

### L2 — WRITE_LOCAL（本地写入）

```yaml
allow:
  - path: "~/.eco/memory-tree/**"
    reason: "Memory Tree 节点写入"
  - path: "~/.eco/.memory/**"
    reason: "审计日志写入"
  - path: "~/.eco/skills/**"
    reason: "技能文件写入（技能孵化）"
  - path: "~/.eco/CHANGELOG.md"
    reason: "版本历史更新"
  - path: "~/.eco/scripts/**"
    reason: "自动化脚本写入"

deny:
  - path: "~/Documents/Obsidian Vault/raw/**"
    reason: "原文只读，禁止修改"
  - path: "~/Documents/Obsidian Vault/wiki/**"
    reason: "知识只读，禁止修改"
  - path: "**/.env"
    reason: "环境变量文件，禁止读取或修改"
  - path: "**/*.key"
  - path: "**/*.pem"
```

### L3 — EXEC（命令执行）

```yaml
allow_auto:
  - command: "python _scripts/lint.py"
    reason: "健康检查脚本"
  - command: "python _scripts/quality_audit.py"
    reason: "质量审计脚本"
  - command: "git *"
    reason: "Git 操作（版本管理）"
  - command: "pip install *"
    reason: "Python 依赖安装"

require_approval:
  - command: "rm -rf *"
    reason: "高危删除操作"
  - command: "chmod *"
    reason: "权限修改操作"
  - command: "sudo *"
    reason: "提权操作"
  - command: "> *"
    reason: "重定向写入（谨慎使用）"
```

### L4 — EXTERNAL（外部网络）

```yaml
require_approval:
  - api: "any"
    reason: "所有外部 API 调用必须审批（MVP 阶段）"
```

---

## 审批流程

```
用户请求 → 风险等级判定
  ├── L1 → 自动执行
  ├── L2 → 自动执行
  ├── L3 (白名单内) → 自动执行
  ├── L3 (白名单外) → 挂起审批收件箱 → 用户审核 → 执行/拒绝
  └── L4 → 挂起审批收件箱 → 用户审核 → 执行/拒绝
```

---

## 风险等级快速判定表

| 操作示例 | 等级 | 自动/审批 |
|:---------|:----:|:---------:|
| 查询知识条文 | L1 | 自动 |
| 检索相似案例 | L1 | 自动 |
| 写入 Memory Tree | L2 | 自动 |
| 运行质量审计 | L3 | 自动（白名单） |
| 安装新 Python 包 | L3 | 自动（白名单） |
| 删除文件 | L3 | 审批 |
| 调用外部 API | L4 | 审批 |
| 联网下载文件 | L4 | 审批 |

---

## 工具风险覆盖（运行时生效）

`agent_core/permissions.py` 按工具名前缀判定默认风险级；以下 `tool_risk_overrides`
块可逐工具覆盖（增删条目后重启会话生效，全部决策写 SM3 审计链 source=permission）：

```yaml
# MCP 法规知识库（eco_kb）五个只读检索工具：L1 自动放行
tool_risk_overrides:
  - tool: execute_code
    level: L3
  - tool: generate_approval_document
    level: L4
  - tool: mcp__eco_kb__eco_search
    level: L1
  - tool: mcp__eco_kb__eco_retrieve
    level: L1
  - tool: mcp__eco_kb__eco_statute_query
    level: L1
  - tool: mcp__eco_kb__eco_graph_query
    level: L1
  - tool: mcp__eco_kb__eco_list_statutes
    level: L1
```
