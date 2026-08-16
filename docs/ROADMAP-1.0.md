# ECO AGENT 1.0 开发路线图

> 目标：从 v5.0.0a8（alpha）收口为 **v1.0.0** 发布级版本。
> 验收口径：`docs/验收标准.md` P0 项全绿 + 补齐 Web API/Web GUI/SDK/插件系统（对标 DSH 工程形态）。
> 编制日期：2026-08 · 随 CHANGELOG 同步更新

---

## 一、现状与差距（DSH 能力对照）

| DSH 能力 | eco-agent 现状 | 差距 |
|---|---|---|
| Web 图形界面 | `eco-desktop/`（Tauri 壳 + 协同编辑组件）、`eco serve`（OpenAI 兼容 API） | ❌ 无浏览器端管理界面（会话/记忆树/技能/工具可视化） |
| 开放 API / SDK | `eco serve`（/v1/models, /v1/chat/completions SSE）、`gateway`（webhook）、`_scripts/eco-knowledge-mcp.py`（MCP server） | 🟡 缺管理型 REST API（会话/记忆/技能/工具）+ 无 SDK 包 |
| 插件扩展系统 | `ecoskills/`（静态 skill）、`agent_core/skill_system.py`（孵化/AB）、`govmcp` 工具注册表 | 🟡 缺第三方插件目录/生命周期/热加载规范 |
| 工程化收口 | CI 三件套、CHANGELOG、RELEASE_SCORECARD、验收标准 | 🟡 缺文档站、版本发布流程未全绿、govmcp 半成品 |

## 二、验收标准 P0 缺口清单（🔴 项）

| 域 | 缺口 | 状态 |
|---|---|---|
| C-01 离线存活 / C-02 云边切换 | 依赖本地模型配置，ProviderRouter 基础就绪 | ⚪ 待补 |
| C-03 统一网关 8 平台 | Web UI / CLI 为骨架 | ⚪ 本次开发（Web GUI） |
| D-03 Token 压缩引擎 | 10万字压缩 <50% + RAG ≥90% | ⚪ 待验证 |
| E-01~E-03 编程智能体基准 | HumanEval/MBPP/OSWorld 评测 harness 未接入 | ⚪ 待接入评测 |
| P-01~P-03 性能基准 | 待实测 | ⚪ 待测 |

## 三、分阶段计划

### Phase 1：基线收口 ✅（2026-08 已完成）
- [x] govmcp / govmcp_tools 提升为顶层包，pyproject 包清单更新
- [x] ToolRegistry API 补齐（register 装饰器重载 / register_batch / ToolInfo.__call__ / category+tags）
- [x] CronScheduler 持久化路径可注入（测试隔离）
- [x] ruff 全绿（含 per-file-ignores 收口）
- [x] 全量测试 100% 通过
- [x] 版本号对齐 5.0.0a8（pyproject + eco/__init__ 兜底常量）

### Phase 2：eco-server 管理 API（进行中）
目标：一个 FastAPI 服务暴露管理型 REST + WebSocket 流式接口，复用 agent_core 能力。

- [ ] `POST /api/v1/chat`（SSE 流式，复用 EcoLoops / cmd_chat 逻辑）
- [ ] `GET/POST /api/v1/sessions`（gateway_core.SessionManager 复用）
- [ ] `GET /api/v1/memory`（Memory Tree 浏览/查询）
- [ ] `GET /api/v1/skills` + `POST /api/v1/skills/reload`（skill_system + ecoskills）
- [ ] `GET /api/v1/tools`（工具目录：govmcp + MCP 连接器）
- [ ] `GET /api/v1/system`（健康/统计/审计摘要）
- [ ] `GET /api/v1/metrics`（token/成本/质量评分）
- [ ] WebSocket `/ws`（L1-L5 循环轨迹实时推送，复用 eco.trace）

### Phase 3：eco-web 浏览器界面
目标：单页应用（React+Vite），挂载于 eco-server，四板块。

- [ ] 会话页（聊天 + 轨迹 + 置信度展示）
- [ ] 记忆树页（浏览/搜索/编辑节点，Obsidian 同步可见）
- [ ] 技能页（skill 列表/启用/孵化历史/AB 结果）
- [ ] 系统页（工具目录、MCP 连接、调度任务、审计日志、指标）

### Phase 4：eco-agent-sdk
- [ ] Python SDK 包（`eco_agent_sdk`）：AsyncClient（chat/stream、sessions、memory、skills、tools）
- [ ] 类型契约 + 文档 + 示例（对接 EcoMind-OS 等应用）

### Phase 5：插件系统规范化
- [ ] `plugins/` 目录规范（plugin.yaml + handler.py + 生命周期 on_load/on_unload）
- [ ] 热加载/卸载 API（对齐 ecoskills 孵化闭环，第三方插件可分发）
- [ ] 插件安全：权限分级（复用 L1-L4 权限闸门）

### Phase 6：工程化收口与发布
- [ ] govmcp 补齐协议层（authorization/elicitation/sampling/tasks/models/transport，从 EcoMind-OS 同步）
- [ ] 评测 harness 接入（EcoBench + HumanEval/MBPP）
- [ ] 性能基准实测（P-01~P-03）+ 7x24 稳定性压测记录
- [ ] 文档站（docs/ 重组 + README 焕新 + 安装/部署指南）
- [ ] 版本 bump 1.0.0 + CHANGELOG + git tag v1.0.0
- [ ] CI release 流程验证

## 四、风险与决策点

1. **govmcp 协议层补齐（1.x 首要工作项）**：govmcp 是对标国内等保合规的政务 MCP 协议栈。
   1.0 已交付国密 crypto、100+ 工具注册表、审批工作流、协议骨架；authorization /
   elicitation / sampling / tasks / models / transport 六个协议层模块列入 **1.1 里程碑**，
   按等保要求补齐后 GovMCPServer 完整可用。
2. **Web GUI 与 eco-desktop 关系**：桌面壳（Tauri）与 Web GUI 并存还是二选一？建议 Web GUI 为 1.0 主交付，desktop 保留为 P2。
3. **E 域评测**：HumanEval/MBPP 依赖外部评测 harness 与 API 配额，建议接入 EcoBench（自带）作为 P0 替代口径。
