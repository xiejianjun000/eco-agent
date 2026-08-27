# ECO AGENT × DSH Web UI 对齐清单

> 目标：eco-agent Web UI 输出与 DSH（deepseek-harness Web GUI，http://127.0.0.1:3080）全部靠齐。
> 方法：以 DSH `packages/client/ui-*` 为规格源，逐项映射到 `eco-agent/web`，每项标注状态。
> 视觉基准截图：`output/playwright/dsh-baseline.png`（本会话 playwright 抓取，模型不可读图，人工核对用）。

## 1. DSH UI 包 → eco-agent 映射

| DSH 包（规格源） | 关键内容 | eco-agent 现状 | 状态 |
|---|---|---|---|
| `ui-layout` | 左侧栏 + 主区两栏布局 | App.tsx：DSH 同构侧栏（新建会话/收起/工作区/搜索/会话树/设置） | ✅ 已对齐（round 2） |
| `ui-conversation` | 消息流、AssistantMarkdown、ReasoningRow、ToolNodeView、CompactionCard | ChatView.tsx：markdown 渲染、思考/工具过程块、DSH 式代码块横幅+复制、工具卡扳手图标、用户消息图标操作行 | ✅ 已对齐（round 4，实测） |
| `ui-trajectory` | 轨迹标签页：Duration/Turns/Calls 树 + 工具栏 + 虚拟滚动账本 | ChatView 右侧轨迹面板：Duration/Turns/Calls 结构 | ✅ 已对齐（round 1，实测通过） |
| `ui-tool` | 工具调用卡（名称/参数/结果/耗时） | process-block call-item | ✅ 已有近似 |
| `ui-theme` | 主题 token（暗/亮） | styles.css：DSH 静态色板 + 别名层 + `html[data-theme='dark']` 双态 + 切换按钮（localStorage） | ✅ 已对齐（round 3，明暗截图存 output/playwright） |
| `ui-sidebar` | 会话列表/搜索/工作区 | 无会话管理页 | ❌ 缺 |
| `ui-message-feedback` | 点赞/踩/复制 | msg-toolbar 已有 | ✅ 已有 |
| `ui-goal` | 目标面板（objective/轮次/暂停/恢复/阻塞/完成） | 无 | ✅ 已对齐（round 7：GoalsView + 后端 goals API，UI 实测创建/暂停状态机） |
| `ui-workflow-run` / `ui-plan` | 工作流编排与计划 | 无 | ✅ 已对齐（round 10：WorkflowView——脚本编辑器+args+三预设（冒烟/三角色执法 DAG/多企业研判）+事件日志+result；UI 实测冒烟 3.7s、DAG 4 子代理 58s） |
| `ui-settings-*` | 设置页（模型/插件/权限预设） | SystemView 只读状态 | ✅ 已对齐（round 8：外观三态切换+主题事件同步、权限闸门运行时开关 API+审计、模型信息；UI 实测） |
| `ui-settings-plugin-inventory` / `ui-slots` / 动态插件循环 | 插件清单、插槽注册、define/run/stop/undefine | 无 | ✅ 已对齐（round 9：PluginsView 三 tab，插件 load/unload/reload + 动态插件全循环 + 插槽数据；UI 与 API 双实测） |
| `ui-subagent` | 子代理目录与状态 | 无 | ✅ 已对齐（round 6：AgentsView 目录/发起/输出流/续聊/中断，端到端实测真实子代理完成） |
| `ui-deliverables` | 产物面板 | side-panel 产物/文档 tab | ✅ 已有近似 |
| `ui-user-questions` | 选项式提问渲染 | 无 | ✅ 已对齐（round 11：助手消息 ```options 块渲染为可点按钮，点击回填输入框） |
| `ui-model-selection` | 模型选择器 | 无 | ✅ 已对齐（round 11：输入行模型下拉，默认/deepseek-chat/qwen-max/claude-sonnet-4，API 实测透传生效） |

## 2. 轨迹页（本轮对齐目标）规格

来自 DSH `packages/client/ui-trajectory/src/client/locales.ts`：

- 工具栏：**Duration**（总耗时，支持 actual duration 切换）/ **Turns**（轮次，可展开/收起）/ **Calls**（工具调用，可展开/收起）
- 账本行类型：`SYSTEM / USER / CONTEXT / COMPACTED / ASSISTANT / TOOL / SUBTOOL`
- 树形：Duration(根) → Turns(组) → Turn n → Calls(组) → 调用明细（名称/参数/结果/耗时）

eco-agent 数据面：`TraceEvent{type: think|tool|answer|correction, round, name, args, result_preview, cost_ms, chars, tools[]}`，
由 `POST /api/v1/chat/stream` SSE 实时推送（`trace_event`），与 DSH 事件账本语义对应。

## 3. 落地顺序（按用户可见性排）

1. ✅ 轨迹面板对齐 Duration/Turns/Calls（round 1，实测）
2. ✅ 侧栏对齐：新建会话按钮 + 会话树 + 搜索框（round 2，实测；logo 已补 round 2.5）
3. ✅ 主题对齐：DSH ui-theme 色板 token + 暗色双态 + 切换（round 3，实测）
4. ✅ 消息流对齐：代码块横幅+复制、用户消息操作行、工具卡扳手图标（round 4，实测）
5. ✅ goal/jobs 面板：GoalsView + AgentsView（round 6/7，实测；AgentsView 轮询停表 bug 已修）
6. ✅ execute_code 沙箱执行（round 5）：handler 注册+闸门放行+docker→os→本地三级降级，端到端实测
7. ✅ 设置页可交互化（round 8）+ 插件/动态插件/插槽（round 9）+ 编排页（round 10）
8. ⏳ 剩余：ui-user-questions（选项式提问）、ui-model-selection（模型选择器）、ui-agent-preset、整体验收双端截图

## 4. 验证方式

- 每项完成后：`cd web && npm run build` 出 dist；`playwright` 打开 http://127.0.0.1:3000(eco web) 与 3080(DSH) 双截图人工比对。
- 纳入 `docs/724-verification-plan.md` L2 Web UI 巡检断言。
