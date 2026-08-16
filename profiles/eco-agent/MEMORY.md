# ECO AGENT — 核心记忆

> **跨会话持久化核心记忆，每次会话自动加载**

---

## 项目状态

- **当前版本**：v0.1.0（初始化阶段）
- **当前阶段**：P0 MVP — Hermes Profile + MCP 桥接
- **项目根目录**：`~/Desktop/ECO AGENT/`
- **知识库**：FlowWiki Obsidian Vault（`~/Documents/Obsidian Vault/`）

## 核心宪法

- **CLAUDE.md**：主 Agent 宪法（身份 + 职责 + 启动协议）
- **SCHEMA.md**：知识宪法（14 维质量标准 + ACE 三阶段审查 + 操作纪律）
- **G 方法论**：Git-based Development Governance（8 大原则）

## 已安装的工具

- 无（MVP 阶段逐步添加）

## 重要的路径

| 路径 | 用途 |
|:-----|:------|
| `_scripts/` | 自动化工具脚本 |
| `skills/` | SKILL.md 格式的执法技能 |
| `profiles/eco-agent/` | Hermes Profile 配置 |
| `memory-tree/` | Memory Tree 数据目录 |

## 当前任务

P0-P3 全阶段开发已完成（v3.0.0）。

### 已激活的服务

| 服务 | 状态 | 说明 |
|:-----|:----:|:------|
| 飞书 Bot | ✅ 已配置 | App ID 经环境变量 FEISHU_APP_ID 配置（不落盘） |
| 飞书 Token | ✅ 已验证 | tenant_access_token 获取成功 |

### 启动命令

```bash
cd ~/Desktop/ECO\ AGENT
bash start_feishu_bot.sh
```
