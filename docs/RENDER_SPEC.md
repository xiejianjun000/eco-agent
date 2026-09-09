# eco 对话渲染规范 v2

> v2 修订（第二轮穿透）：v1 只研究了 `conversation-render` 中栏消息渲染，
> 补入三块遗漏 —— 流式缓冲参数、右侧产物面板、Plan 模式闭环（§6.5），
> 并补 §9 记录提取路径与两处踩坑，便于复核。

> 来源：对 WorkBuddy `conversation-render` 包构建产物的代码级重建。
> 该产物未混淆、保留原始 TSX 注释与源码路径，因此以下结构与数值是**读出来的**，
> 不是观察 UI 猜出来的。但仍属静态重建 —— 我无法点击其 GUI 验证交互细节。
>
> 提取方式：`app.asar` 头部 JSON 索引 → `renderer/assets/src-*.js`（9.9MB）
> 与 `src-*.css`（1.4MB）。
>
> **不复制其代码**：类名全部换成 eco 自己的 `eco-` 前缀，
> 数值按测量值重新实现。WorkBuddy 类名为 `cr-`（conversation-render）。

---

## 0. 一句话结论

WorkBuddy 的"好看"不来自某个组件，而来自三条纪律：

1. **一个工具一个视图** —— 33 个独立 view，不是一套通用渲染器套所有工具。
2. **展开只加内容，不换皮** —— 三段式头部恒在，展开只在其下方追加 children。
3. **全局低对比** —— 工具区所有文字统一用 `text-tertiary`（约 50% 灰），
   只有正文答案用 `text-primary`。工具块在视觉上"退到背景里"。

eco 当前的问题正对应这三条：所有工具走同一套渲染、展开时整块换成裸行、
工具文字与正文同等权重，于是"混在一起"。

---

## 1. 三段式头部（ToolHeader）

这是整个体系的地基。任何工具块的头部只有这几个槽位，顺序固定：

```
[icon] [statusText] [primaryContent] [secondaryInfo] ............ [arrow] [actions]
 14px    动词         对象(可省略)      计数/补充         右侧
```

对应关系（这是"不混在一起"的关键）：

| 槽位 | 语义 | 例 |
|:--|:--|:--|
| `icon` | 工具类别，失败时替换为 FailedIcon | 🔍 |
| `statusText` | **动词**，执行中/完成两种文案 | 搜索中… / 已搜索 |
| `primaryContent` | **对象**，可省略；超长省略号截断 | "娄底市空气质量" |
| `secondaryInfo` | 计数或补充，12px 更小 | "12 条" |
| `arrow` | 可展开时才有，默认 opacity 0 | ⌄ |
| `actions` | 右侧按钮，点击不触发展开 | [打开] |

行为要点（读自实现）：

- `error=true` 时 icon 换 FailedIcon，但**头部结构不变**。
- `isExecuting=true` 时不显示 icon，给 status 加 `--loading`。
- 空值槽位直接不渲染节点（`!= null && !== ""`），不占位。
- 头部整体可点击展开，但 `actions` 内部 `stopPropagation`。
- 双击不触发展开（`event.detail > 1` 时 return）—— 防误触选中文字。

### 精确样式（测量值）

```
.tool-head          display:flex; align-items:center; gap:8px;
                    min-width:0; font-size:14px; line-height:1.75;
                    color: text-tertiary
.tool-head__icon    14×14; flex:none; inline-flex 居中
.tool-head__status  flex:none
.tool-head__primary min-width:0; overflow:hidden;
                    text-overflow:ellipsis; white-space:nowrap
.tool-head__secondary  font-size:12px; flex:none
.tool-head__arrow   opacity:0; transform:rotate(-90deg);
                    margin-right:-4px;
                    transition: transform .24s cubic-bezier(.2,.8,.2,1),
                                opacity .18s ease, color .18s ease
```

注意 `gap:8px` 与 `font-size:14px / line-height:1.75` 是整个工具区的节奏基准。
`primaryContent` 是唯一允许伸缩的槽位，其余 `flex:none`。

---

## 2. 展开容器（ToolExpandable）

```
ToolExpandable({ canExpand, defaultExpanded, expand, autoScroll,
                 disableMotion, contentClassName, children, actions,
                 ...headerProps })
  └─ ToolHeader({ ...headerProps, actions, collapsible, expanded, onToggle })
  └─ div.tool-exp__content-shell[--expanded]   ← 仅 expandable 时存在
       └─ div.tool-exp__content
            └─ children
```

**关键纪律**：`...headerProps` 原样透传给 ToolHeader，
`children` 只出现在 shell 内部。展开与否，头部完全一致。

其他读到的细节：

- `expandable = canExpand && children != null` —— 没有内容就不给箭头。
- `expand` 受控 prop 与内部 state 并存：外部 true→false 才强制收起，
  false→true 才强制展开（用 `prevExpandRef` 判沿），避免与用户手动展开打架。
- `autoScroll` 走 `useStickyAutoScroll`，仅在展开时生效 —— 流式输出时黏底。
- `aria-hidden` 跟随展开状态。

```
.tool-exp            display:flex; flex-direction:column; width:100%
.tool-exp__content   opacity:0; transform:translateY(-6px)   ← 收起态
```

展开动画由 `useExpandMotion` 驱动 shell 高度，内容做 6px 位移淡入。

---

## 3. 一个工具一个视图

这是与 eco 现状差别最大的一点。WorkBuddy 有 **33 个** 独立 view：

```
web-search      web-fetch        read-file       write-file
execute-command list-files       delete-files    read-lints
todo-write      plan             enter-plan-mode exit-plan-mode
task            team             skill           question
mcp-call-tool   mcp-display      mcp-match-tool  fetch-mcp-resource
image-gen       agent-mail       automation      integration
dispatch-specialist  specialist-tools  send-message
conversation-search  search-reference  search-tool
connect-cloud-service  defer-execute  completion
open-result-view  visualizer-read-me  weixinpay  compact-misc
```

### 注册与路由

```js
defineTool({ match, convert, Component, id })

matchPriority(match, tool):
  string        → name === match      ? EXACT(10) : NONE(0)
  string[]      → includes(name)      ? EXACT(10) : NONE(0)
  (name, tool)  → number | boolean    (可返回 DEFAULT(1) 做兜底)
```

三档优先级 `NONE:0 / DEFAULT:1 / EXACT:10`，让 MCP 这类动态工具
可以用函数匹配吃下一整族（如 `mcp__*`），同时不挡具体工具的精确注册。

### 兜底与容错

- 未命中任何 view → `unknown-tool` 视图，不是白屏也不是裸 JSON。
- 每个 view 外包一层 `ToolErrorBoundary`（class component + `getDerivedStateFromError`），
  单个工具渲染崩溃不会带走整条对话。
- `ToolbarShell` 往 DOM 上打调试属性：

  ```
  data-tool-name / data-tool-status / data-tool-view / data-tool-call-id
  ```

  `data-tool-view` 为 `"fallback"` 即表示走了兜底 —— 这对我们做 DOM 断言极有用。

### 单个 view 的标准写法（以 web-search 为例）

```js
function WebSearchView({ toolName, toolCallId, status, emit, icon, data }) {
  const phase     = toToolPhase(status)
  const executing = isRunningPhase(status)
  return ToolExpandable({
    icon,
    statusText:     executing ? "搜索中…" : "已搜索",   // 动词
    isExecuting:    executing,
    error:          phase === "error",
    primaryContent: data.query,                        // 对象
    primaryTitle:   data.query,                        // hover 全文
    canExpand:      phase === "success" && data.results.length > 0,
    children:       <结果行列表 />,
  })
}
```

三点值得抄：
1. `statusText` 随执行态切换动词，不是静态标签。
2. `canExpand` 由**有无内容**决定，不是恒 true。
3. 交互统一走 `emit(event, payload)` 上抛，view 自身无副作用。

---

## 4. 思考块（reasoning）

```
.reasoning                        font-size:12px
.reasoning .collapse__header      font-size:14px
.reasoning .collapse__content-inner
    margin: 8px 0 4px 0
    padding-left: 12px
    border-left: 4px solid var(--reasoning-border, --border-default)
    line-height: 20px
    max-height: 200px            ← 限高，超出内部滚动
    overflow-y: auto
    scrollbar-width: thin; 滚动条 6px，thumb 圆角 3px
```

流式时的处理很讲究 —— 文字本身做渐变，**上实下虚**：

```
.reasoning .collapse--streaming .collapse__content-inner
    background: linear-gradient(180deg, text-primary 20%, text-tertiary 80%)
    background-clip: text
    -webkit-text-fill-color: transparent
    background-attachment: local        ← 关键：渐变跟随内容滚动而非视口
```

代码高亮片段需排除在渐变外（`[class^=hljs-]` 恢复 `-webkit-text-fill-color: initial`）。

思考块比工具块更小（12px vs 14px），左边框而非卡片 —— 层级上更"轻"。

---

## 5. 主题变量

明暗两套，工具区几乎只用 tertiary：

| 变量 | 亮色 | 暗色 |
|:--|:--|:--|
| `text-primary` | `rgba(0,0,0,.9)` | `rgba(255,255,255,.92)` |
| `text-secondary` | `rgba(0,0,0,.7)` | `rgba(255,255,255,.65)` |
| `text-tertiary` | `rgba(0,0,0,.5)` | `rgba(255,255,255,.45)` |
| `border-default` | `#ebebeb` | `#2a2c31` |
| `bg-canvas` | `#fafafa` | `#141414` |
| `bg-elevated` | `#ffffff` | `#242629` |
| `bg-hover` | `rgba(0,0,0,.05)` | `rgba(255,255,255,.06)` |

**这是"不混在一起"的视觉基础**：工具/思考全部 tertiary，
正文答案 primary。对比度差异本身就在做信息分层，不需要额外分隔线。

---

## 6. 与 eco 现状的差距

| 维度 | WorkBuddy | eco 现状 | 动作 |
|:--|:--|:--|:--|
| 工具视图 | 33 个独立 view + 优先级路由 | 一套通用渲染 | 建 registry，先做高频 6 个 |
| 展开 | 头部恒在，仅追加 children | 换成裸 `dsh-*` 行 | 已修（上一轮） |
| 头部 | icon/动词/对象/计数 四段 | 已有 beat 三段 | 补 `secondaryInfo` 与 actions |
| 文字层级 | 工具全 tertiary | 与正文同权重 | 引入 token 分层 |
| 思考块 | 12px + 左边框 + 限高 200 + 流式渐变 | 无独立样式 | 新建 |
| 兜底 | unknown-tool + ErrorBoundary | 无 | 补 |
| 可测性 | `data-tool-view` 等四个属性 | 无 | 补（便于 DOM 断言）|
| 流式节奏 | 7 参数帧控制 + 无障碍降级 | 有 resetKey，无节奏与降级 | 补降级（硬要求），节奏可选 |
| 产物面板 | 三分区 + HTML iframe 实时预览 | DocDrawer 只做文档预览 | 补产物列表与 iframe |
| Plan 模式 | 完整状态机 + 一次性批权限 | 无 | 不引入，仅借"一次性批权限" |

---

## 6.5 三块补充（v1 遗漏，第二轮穿透补齐）

v1 只研究了 `conversation-render`（中栏消息渲染），漏掉了三个模块。
以下内容同样是从 `app.asar` 读出来的，提取路径与核实方式见每小节。

### 6.5.1 流式文本缓冲（精确参数）

v1 说"流式渐变"只讲了视觉，漏了**节奏控制**。真实实现带完整参数表，
产物里保留了源码路径 `packages/conversation-render/src/list-like-render/streaming-text/config.ts`：

```
targetIntervalMs:   40      每帧目标间隔（≈25fps，不是逐字定时器）
speedDivisor:       28      剩余字符数 ÷ 28 = 本帧应吐字数
minCharsPerTick:    1
maxCharsPerTick:    4       上限 4 字/帧，防长文本瞬间刷屏
accelFactor:        0.2     落后目标时的加速系数
decelFactor:        0.08    接近目标时的减速系数（比加速小 2.5 倍 → 缓停）
fastDrainThreshold: 0
```

Hook 形态：`useStreamingTextBuffer(targetText, { isStreaming, drainOnFinish, enabled, resetKey })`

三个 v1 漏掉的关键机制：

1. **`drainOnFinish`**：流结束时排干缓冲，避免最后几个字被丢弃。
2. **`resetKey`**：换消息时重置缓冲，否则上一条的残余会串到下一条。
3. **无障碍降级**：`canAnimate = enabled && hasRaf() && !prefersReducedMotion()`
   —— 系统开了"减少动态效果"就直接全量显示，不做动画。
   这一条文档与 v1 都没提，但对可访问性是硬要求。

输入框侧对应两个开关：`allowSendWhileStreaming = false`（生成中禁止再发）、
`preferCancelWhileStreaming`（生成中把发送按钮变成取消）。

> eco 现状：`deltaReset` 测试 5 项已覆盖 resetKey 语义，
> 但没有帧节奏控制，也没有 `prefers-reduced-motion` 降级。

### 6.5.2 右侧产物面板（ProductPanel / DetailPanel）

v1 完全没覆盖。语言包文案逐字如下（`renderer/assets/zh-cn-*.js`，已核对）：

```
panel.hideProductPanel       收起右栏
panel.showProductPanel       展开右栏
panel.hideDetailPanel        隐藏详情面板
panel.showDetailPanel        显示详情面板
detailPanel.selectArtifact   请选择一个产物查看详情     ← 空态

artifactSlot.title           任务产生制品（{count}个）：
artifactSlot.viewAll         查看所有产物 ({count})
artifactSlot.filesTitle      文件变更（{count}个）：
artifactSlot.viewFileChanges 查看所有变更 ({count})
artifactSlot.sourcesTitle    引用来源 ({count})
artifactSlot.sourcesTooltip  引用 {count} 篇资料作为参考
artifactSlot.openPreview     打开网页预览 →
artifactSlot.openInBrowser   在浏览器中预览
```

结构上是三个分区：**制品 / 文件变更 / 引用来源**，各自带计数与"查看全部"。
组件文件独立打包：`artifact-slot-panel-*.js`（30KB）、`detail-panel-wrapper-*.js`（203KB）。

核心行为：**HTML 类产物自动在面板内打开实时预览**（iframe），
并额外给"在浏览器中预览"出口；非 HTML 走对应预览器
（`pptx-preview` / `pdf-preview` / `sheet-preview` / `excalidraw-preview`）。

> eco 现状：`DocDrawer` 已按产物抽屉形态实现，但只做文档预览 ——
> 没有产物列表、没有三分区计数、没有 HTML iframe 实时预览。
> 后端已具备条件：`present_files` 工具 + `/api/documents` 下载白名单。

### 6.5.3 Plan 模式闭环

v1 没覆盖。真实文案是一条完整状态机（已逐字核对）：

```
tool.enterPlanMode.entering          正在进入规划模式...
tool.enterPlanMode.entered           已进入规划模式，正在探索并设计实现方案。
tool.enterPlanMode.declined          规划模式请求被拒绝
tool.exitPlanMode.planReady          方案已就绪
tool.exitPlanMode.permissionsRequested  请求 {count} 项权限：
tool.exitPlanMode.yes                开始执行            ┐
tool.exitPlanMode.keepPlanningBtn    调整计划            ├ 三按钮
tool.exitPlanMode.exitPlanModeBtn    退出规划模式         ┘
tool.exitPlanMode.approved           方案已批准，开始执行...
tool.exitPlanMode.keepPlanning       调整计划中...
tool.exitPlanMode.exited             已退出规划模式
tool.exitPlanMode.modeSyncFailed     切换执行模式失败，会话可能已被回收，请重新发送消息以继续。
```

值得单独记的是最后一条：**模式切换失败有专门的用户可行动文案**，
而不是抛一个技术错误。这与 eco 的"探测失败只能得出探测失败"是同一种诚实。

关键设计：退出规划时**一次性声明需要几项权限**（`permissionsRequested`），
用户在一个确认点批准全部，而不是执行途中逐个弹窗打断。

> eco 现状：无 Plan 模式。eco 走的是"任务一次做完，禁止半途反问"，
> 与 Plan 模式是两种取向 —— 不是缺口，是分歧，见 §7。

---

## 7. 不照搬的地方

- **锚点策略**：WorkBuddy 取"最长 + 最后"一条旁白做锚点。
  eco 的旁白普遍 15–25 字且长度均匀，套用会几乎总是取到最后一条。
  eco 保持"全部旁白皆为锚点"。
- **并行调度**：eco 三路并行约 20s，串行约 60s，保留并行，
  仅在 UI 上重建节奏感。
- **类名与图标**：全部使用 eco 自有前缀与图标，不引用其资源。
- **Plan 模式**：不引入。WorkBuddy 用"进入规划 → 方案就绪 → 批准执行"
  换取可控性；eco 的宪法是"任务一次做完，禁止半途反问"（提示词第 11 条）。
  两者是取向分歧，不是能力缺口 —— 军哥的执法场景要的是问一次拿到结论，
  不是先审一份方案。**但 Plan 模式里"一次性声明全部权限"这条值得借**：
  eco 现在是执行途中逐个弹权限，L4 操作多时会连续打断。
- **无障碍降级要照搬**：`prefers-reduced-motion` 降级是硬要求，不是可选项。

---

## 8. 验收方式

不看截图，用 DOM 断言：

1. 折叠态与展开态，`.eco-tool-head` 节点数必须相等（展开不换皮）。
2. 展开后 `.eco-tool-head` 仍在，且 `statusText` 文本不变。
3. 任一工具块的 `data-tool-view` 不得为 `fallback`（高频工具已覆盖）。
4. 工具区文字 `color` 计算值等于 tertiary token。
5. 不得出现 `mcp__` 原始工具名（已有 stripToolNames 保障）。

补充三项（对应 §6.5，v1 缺）：

6. 系统开启"减少动态效果"时，流式文本必须一次全量显示，不做逐帧动画。
7. 产物面板打开 HTML 类产物时，必须存在 iframe 节点且 `src` 指向真实落盘路径；
   同时必须提供"在浏览器中预览"出口（不能只能在面板内看）。
8. 产物面板三分区（制品 / 文件变更 / 引用来源）的计数必须与实际条目数一致 ——
   计数与列表不一致比不显示计数更糟。

---

## 9. 溯源与核实方式

本文档两轮研究的提取路径，便于下一个人复核而不必重走：

| 轮次 | 目标 | 提取路径 |
|:--|:--|:--|
| v1 | 中栏消息渲染 | `app.asar` → `renderer/assets/src-*.js`（9.9MB）+ `src-*.css`（1.4MB）|
| v2 | 流式/产物/Plan | `renderer/assets/zh-cn-*.js`（573KB，语言包）、`src-CocHqt_k.js`（10.4MB）、`artifact-slot-panel-*.js`、`detail-panel-wrapper-*.js` |

解包方式：`app.asar` 前 16 字节含头部长度，其后是 JSON 索引，
再往后是按 `offset`/`size` 定址的文件区。索引里 `app.asar.unpacked`
的条目**没有 `offset` 字段**，遍历时必须跳过，否则 KeyError。

CSS Modules 编译后类名带 hash（如 `_grid_1ens7`），
**直接 grep `cr-tool-diff` 这类源码前缀在 CSS 里搜不到** ——
前缀只存在于编译前源码与 JS 侧的类名映射中。
v2 核实时先在 CSS 里搜不到，一度以为文档有误，改搜 JS 产物才确认属实。
这一步记下来，避免下次重复误判。

另一个可信度依据：JS 产物**未混淆**，保留了原始源码路径注释
（如 `../../packages/conversation-render/src/list-like-render/streaming-text/config.ts`），
所以参数表与文案是**读出来的**，不是观察 UI 猜的。
但静态重建有边界：**交互时序与真实手感无法从代码验证**，
本文档不对"用起来什么感觉"下结论。
