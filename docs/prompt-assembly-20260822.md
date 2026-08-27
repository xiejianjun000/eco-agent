# DSH 式模块化提示词组装系统 · 落地档案

> 日期：2026-08-22 · 目标 goal-090ce07c · 已完成并实测

军哥要求：按 DSH"一切皆插件"哲学改造 eco-agent 的系统提示词——
从 monolithic 提示词转向可插拔、可组装、可溯源的模块化提示词系统。

## 一、核心组件

| 组件 | 路径 | 说明 |
|:-----|:-----|:-----|
| 片段注册表 | `agent_core/prompt_sections.py` | PromptSection 数据类 + Registry：register/unregister/list/assemble；标准优先级（safety=0 首位不可动摇 → persona → 工具指南 → 阶段 → 规则 → 上下文 → 技能 → 经验 → 自定义 → 注入=90）；content 支持 callable 实时求值 |
| 组装引擎 | `agent_core/prompt_engine.py` | 重构 build_system_prompt：基础片段 + 每请求动态片段（按优先级插入）+ 运行时注入 + extra；新增 register_section / list_sections / overview |
| 建议提示词 | `agent_core/suggest.py` | 对标 DSH suggest-prompt：规则引擎（工具追问/落盘纪律/阶段推进/错误重试），ECO_SUGGEST_LLM=1 可 LLM 增强 |
| 管理 API | `server/api/prompt.py` | overview / sections 注册移除 / inject 注入 / persona 人设切换 |

## 二、组装结构（DSH 式）

```
【安全准则】(safety=0, 硬编码+SOUL硬边界, 不可覆盖)
【人设】(persona=10, SOUL.md)
【工具能力】(tool_guidance=30, 动态拉取 tools_registry)
【执法阶段】(phase=35, 巡查/文书/评查 状态机)
  ↑ 以上为持久注册片段（插件可 register_section 覆盖/新增）
【规则·法典与工具纪律】(rules=25, 每请求)
【工具指南·已挂载 MCP】(tool_guidance=30, 每请求)
【动态上下文】(context=40, 日期/阶段/工作区, 每请求)
【技能注入】(skill=45, 触发词匹配 ecoskills)
【历史经验】(lessons=50, 自愈闭环教训)
  ↑ 以上为每请求动态片段（chat.py _dynamic_prompt_sections）
[source] 运行时注入内容 (injection=90, 校验+SM3审计)
```

## 三、安全设计（不因模块化而削弱）

- **安全层永远第一**：safety 片段 priority=0，任何插件/注入无法排到它前面；
  `validate_injection` 拦截试图覆盖安全层/绕过监管的注入，拒绝并写 SM3 审计链。
- **全程审计**：片段注册/移除、注入接受/拒绝、阶段切换全部写 SM3 链
  （source=prompt_api / phase_switch）。
- **注入校验**：违规注入（"忽略安全准则"等）实测直接拒绝。
- **建议零风险**：建议只是 UI 快捷气泡（点击填入输入框），不自动执行。

## 四、实测结果

| 项 | 结果 |
|:---|:-----|
| /prompt/overview | 4 基础片段 + 注入统计 + 组装预览（assembled 2210 字） |
| POST /prompt/sections | 插件式片段注册/覆盖成功（priority 排序正确） |
| POST /prompt/inject | 合法注入接受；"忽略安全准则"拒绝 + 审计 |
| POST /prompt/persona | inspection/documentation/review 切换生效，非法值 400 |
| 聊天建议 | 冷水江统计提问 → 3 条建议（线索详情追问/文书阶段推进/落盘报告） |
| Web UI | 建议气泡（虚线胶囊，点击填入输入框），dist 已构建上线 |
| 测试 | 新增 18 项全绿；全量仅 cnemc 网络测试一次抖动（重跑通过） |
| 兼容性 | 既有 prompt/soul/corrections/workspace/server_api 测试全绿，输出顺序不变 |

## 五、与 DSH 的对应关系

| DSH | eco-agent |
|:----|:----------|
| 系统提示词组装注册表（插件贡献 sections） | PromptSectionRegistry + register_section |
| 标准模式预设（persona/工具/规则） | 基础四片段（safety/persona/工具能力/阶段） |
| dsh-prompt-inject（动态注入） | POST /prompt/inject（校验+审计） |
| dsh-whale-persona（人设插件） | POST /prompt/persona（三阶段执法状态机） |
| @studyzy/dsh-suggest-prompt（每回合建议下一条提示词） | agent_core/suggest.py + Web 快捷气泡 |
| 动态上下文注入（DSH_CWD 等） | 动态上下文片段（日期/阶段/工作区） |

## 六、后续可做

- .dsh 插件包格式适配器（读取 .dsh 插件中的 prompt section 贡献，映射进本注册表）
- 提示词片段可视化编辑界面（Web 端直接增删片段 + 预览组装效果）
- 建议提示词的点击率/采纳率统计（suggest 质量反馈闭环）
