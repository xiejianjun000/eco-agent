# DSH 生态插件适配 eco-agent 清单（2026-08-24 调研）

> 来源：deepseek-harness examples/ + packages/ 能力目录 + awesome-dsh-plugin 社区清单
> + 本机 _git-check/ 已 clone 的军哥生态插件仓库。适配结论分级：**直接复用 / 借鉴实现 / 不需要**。

## 一、直接可挂（已在本机，MCP 即插即用）

| 插件 | 来源 | eco 现状 | 动作 |
|:---|:---|:---|:---|
| dsh-eia-review-plugin（环评审查 MCP） | _git-check/ | 已作为 `mcp__eia__*` 挂载（4 工具） | ✅ 已用；其 Chroma 向量库降级为 keyword（ECONNREFUSED），可选本地起 Chroma |
| eco-sthjzf-mcp / eco-wryzxjc-mcp / permit-management-mcp（三平台 MCP 版） | _git-check/ | govmcp 直连实现已存在 | 保留直连（延迟低、审计链在册）；MCP 版作为冗余通道 |

## 二、官方参考实现（借鉴设计，不直接装）

| 插件 | 用途 | 适配点 |
|:---|:---|:---|
| examples/mcp-memory（Memorix / MCP Reference Memory / Engram） | 记忆 MCP | eco 已落地**本地向量检索记忆**（agent_core/memory_index.py，n-gram 哈希+覆盖度打分，零依赖）；若后续要语义 embedding 可换 Memorix |
| examples/web-schedule | 定时调度 | eco 的 cron/scheduler 已有——可补**督察整改到期提醒**任务模板 |
| packages/goal / subagent / workflow | 目标循环/子代理/工作流 | eco 已有 goal.py/subagent/workflow 对应实现，对标差距在编排深度，逐步补齐 |

## 三、社区插件适配建议（按 eco 业务价值排序）

| 社区插件 | 功能 | 适配 eco 的方案 |
|:---|:---|:---|
| **dsh-visualize / dsh-genui**（对话内生成式 UI：交互式 HTML 卡片/图表） | 数据分析可视化 | **最高优先**：eco 的数据分析报告（AQI/超标研判）可渲染成可交互卡片；前端已有预览面板基础 |
| **dsh-file-mentions**（回复中文件路径可点击） | 产物定位 | save_document 返回的路径在聊天里做成可点击 chip（Web 端小改） |
| **dsh-at-file / dsh-annotation**（@file 引用/选中批注） | 案卷引用 | 案卷评查场景：选中案卷段落→批注→随消息发送 |
| **dsh-web-review**（隔离网页预览+元素批注） | 文档校对 | 配合 tdocs 预览面板，执法文书校对场景 |
| **dsh-smooth-stream**（丝滑流式渲染） | 体验 | 前端流式渲染微调（当前 6 字切片回放可换增量平滑） |
| **dsh-hud**（Git/MCP/技能/用量状态面板） | 运维可见性 | eco 系统页已有部分；补"已挂 MCP/政务登录态"一目了然面板 |
| dsh-multi-chat / dsh-focus-chat | 多会话/聚焦视图 | 执法场景低优先 |
| dsh-balance-meter 等计费类 | 用量计费 | 军哥账号余额监控可选 |

## 四、结论

- **不装即赢**：eco 已自建 govmcp 直连（延迟/审计优于外挂 MCP）、本地向量记忆（无外部依赖）、Cordis 组合装配（工具/能力插件化样板已落地）。
- **值得做的三个**：① dsh-visualize 式交互图表卡片（数据分析场景刚需）；② file-mentions 产物可点击；③ web-schedule 式整改到期提醒。
- 需要时说一声，我按插件样板逐个落地。

## 五、质量与稳重类增强（本轮已落地）

| 机制 | 来源对标 | eco 落地 |
|:---|:---|:---|
| guard（回答护栏） | DSH guard 包 | **质量门禁 `_quality_gate`**：法条号↔法典原文一致性核验（subprocess 直查+重合度判定）、'共N个'与表格行数一致性核验；不合格自动纠偏重写一次（两条回答路径全覆盖），零额外 LLM 成本 |
| compaction（上下文压缩） | DSH compaction 包 | `_build_messages` 历史 6000 字预算：超限保留最近 8 条、单条超 3000 字首尾截断——长对话不撑爆上下文 |
| feedback（反馈学习） | DSH feedback 包 | eco 已有 lessons.jsonl 自愈闭环（23 条教训实证）+ 向量记忆库（语义回忆）——用户反馈/踩坑自动沉淀为下次注入 |

三高保障链：**高质量**（条号核验+纠偏重写）→ **高水平**（结构化输出+风格锚）→ **高效果**（工具直连真实数据+表格豁免不漏行）。
