# eco 对话渲染规范 v1

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

---

## 7. 不照搬的地方

- **锚点策略**：WorkBuddy 取"最长 + 最后"一条旁白做锚点。
  eco 的旁白普遍 15–25 字且长度均匀，套用会几乎总是取到最后一条。
  eco 保持"全部旁白皆为锚点"。
- **并行调度**：eco 三路并行约 20s，串行约 60s，保留并行，
  仅在 UI 上重建节奏感。
- **类名与图标**：全部使用 eco 自有前缀与图标，不引用其资源。

---

## 8. 验收方式

不看截图，用 DOM 断言：

1. 折叠态与展开态，`.eco-tool-head` 节点数必须相等（展开不换皮）。
2. 展开后 `.eco-tool-head` 仍在，且 `statusText` 文本不变。
3. 任一工具块的 `data-tool-view` 不得为 `fallback`（高频工具已覆盖）。
4. 工具区文字 `color` 计算值等于 tertiary token。
5. 不得出现 `mcp__` 原始工具名（已有 stripToolNames 保障）。
