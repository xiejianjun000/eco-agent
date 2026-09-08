# WorkBuddy 穿透式对比 · eco 能力缺口清单

> 来源：`/Applications/WorkBuddy.app/Contents/Resources/app.asar.unpacked/resources/plugins/workbuddy-builtin/`
> 该目录为**明文未打包**资源，可直接读取。此前判断「提示词在服务端」是错的 —— 它一直在本地。
> 所有结论均为源码级还原，非 GUI 操作观察。

## 一、WorkBuddy 能力架构（实测）

`marketplace.json` 声明 32 个内置插件，六个类别：

| 类别 | 数量 | 内容 |
|---|---|---|
| `skill` | 18 | ardot-design-*（6）、recommend-*（2）、skill-creator、library、wb-finance 等 |
| `builtin-plugin` | 5 | weixinpay、tencent-docs-plugin、sheetagent、tencent-pptx、tencent-docx |
| `interaction` | 4 | craft / ask / plan / expert |
| `welcomeMode` | 3 | code / work / design |
| `template` | 1 | prompt-common（共享提示词片段） |
| `mcp-app` | 1 | ardot-mcp-app |

渲染层另有 40 个 `defineTool`（`src.js`），是 UI 呈现清单，与能力清单不等价。

## 二、三层分工（`ardot-design-router/SKILL.md` 实证）

```
Router skill   → 只做意图分类，不干活（disable-model-invocation: true）
Domain skill   → 领域流程与规范
MCP            → 真正的执行能力（"All canvas manipulation goes through the ardot MCP tools"）
```

## 三、关键机制与 eco 现状

### 3.1 Skill frontmatter 契约

WorkBuddy 用两个字段控制 Skill 的可见性与权限：

| 字段 | 作用 | 实例 |
|---|---|---|
| `allowed-tools` | 声明该 Skill 需要哪些工具，系统据此授权 | `recommend-connectors`: `search_plugins suggest_plugin_install` |
| `disable-model-invocation` | 模型不可自主调用，只能由路由器显式加载 | 6 个 ardot skill 全部为 `true` |
| `user-invocable` | 用户是否可直接触发 | `ardot-design-router`: `false` |

**eco 现状**：Skill 有 SKILL.md 与 frontmatter，但**无 `allowed-tools` 授权语义**，也无 `disable-model-invocation` 分层。
**归因：插件（宿主加载器）+ Skill（格式约定）**

### 3.2 模式级工具白名单（`interactionmode/*/fragments/interaction.md`）

| 模式 | 工具数 | 特征 |
|---|---|---|
| ask | 10 | 只读：Read/Glob/Grep/WebFetch/WebSearch，**无 Write、无 Bash** |
| craft | 37 | 全能力 |
| plan | 37 | craft + EnterPlanMode/ExitPlanMode |
| expert | 37 | 同 plan |

还有 `Defer(X)` 语法表示延迟加载（如 `Defer(ImageGen)`、`Defer(LSP)`）。

**eco 现状**：`_codex_tools()` 一次性给出 44 个工具，**无模式分层**，只读场景也拿到 shell 与写文件。
**归因：插件（提示词装配层）**

### 3.3 旁白硬规则（`craft/fragments/tool-use.md`）

> `NEVER mention specific tool names in user-facing messages or status descriptions.`

**eco 现状**：实测旁白出现「再用 glob 扫全部 README」「先并行查工具目录」——**直接违反**。
**归因：插件（提示词规则）**

### 3.4 agent loop 第 8 条（`craft/fragments/agent-loop.md`）

> 最终回复必须 carry forward「被折叠或隐藏的中间工具调用、观察与进度消息」中的重要结果。

配套 `<final_answer_instructions>`：逐条要求复述命令输出、文件路径、变更、结论、错误、未决风险；多问必须逐问作答或明确标记未解决；**上限 50-70 行**。

**eco 现状**：有总结指令，但无「折叠内容必须带出」的显式约束，也无行数上限。
**归因：插件（提示词规则）**

### 3.5 present_files 契约（`result-presentation.md`）

产出可视结果时，**本轮最后一个工具调用必须是 `present_files`**；HTML 自动开预览面板，其它类型显示为 artifact 卡片；只呈现新产出、不呈现只读过的文件。

**eco 现状**：有 `save_document`/`generate_pptx`/`chart_render`，但**无统一的成果呈现入口**，产物散落在过程块里。
**归因：插件（工具 + UI 卡片）**

### 3.6 Plugin 推荐闭环（`prompt-common/fragments/plugin-recommendation.md`）

Connector（外部服务/MCP/授权）与 Expert（专业角色）两类；`search_plugins` 查真实候选 → `suggest_plugin_install` 渲染卡片；禁止编造 ID、禁止文字列表代替卡片、一次一类最多 3 个、用户拒绝后同轮不得重复推荐。

**eco 现状**：无。
**归因：MCP（候选来源）+ 插件（卡片 UI）+ Skill（推荐流程）**

## 四、按支撑方式归类的缺口

### 需要 MCP 支撑
| 缺口 | 说明 |
|---|---|
| 设计/画布能力 | WorkBuddy 全部走 ardot MCP；eco 无对应域，**判定为不适用**（eco 是环保执法域，非设计工具） |
| Connector 候选来源 | `search_plugins` 需要真实插件市场；eco 无市场，可降级为本地 MCP 清单 |

### 需要插件支撑（宿主/提示词/UI）
| 缺口 | 优先级 |
|---|---|
| 模式级工具白名单（ask 只读 / craft 全能力） | 高 |
| 旁白禁提工具名 | 高 |
| 最终回复 carry-forward + 行数上限 | 高 |
| `present_files` 统一成果呈现 | 中 |
| Skill `allowed-tools` 授权 | 中 |

### 需要 Skill 支撑
| 缺口 | 优先级 |
|---|---|
| `disable-model-invocation` / `user-invocable` 分层 | 中 |
| Router → Domain 两级 Skill 结构 | 低（eco 现有 skill 数量少，暂不需要路由层） |

## 五、明确不做的项（附理由）

| 项 | 理由 |
|---|---|
| ardot 设计系列（6 个 skill + MCP） | 领域不符。eco 是环保执法/大气溯源/环评审查，不做 UI 设计与画布 |
| weixinpay | 无支付场景 |
| tencent-docs / docx / pptx / sheetagent | eco 已有 `tdocs_upload_html` 与 `generate_pptx`，能力重叠 |
| team_create / team_delete / dispatch_specialist | eco 有 subagent，但用户明确要求单体可控，不引入多角色团队 |
| NO SUB-AGENTS 硬规则 | WorkBuddy 在设计场景禁用子代理；eco 场景不同，保留 subagent |
