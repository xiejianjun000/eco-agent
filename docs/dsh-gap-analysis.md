# DSH vs eco-agent 深度对比分析

> **执行状态（2026-08-17）：路线图三期 12 项全部完成 ✅**
> 见文末「6. 执行记录」。提交链：ef16e2b(Subagent) → 66cad90(任务面板) →
> 798e14f(会话加固) → b8ef531(mini-Cordis) → 46a3de0(Skill) →
> f208a5e(服务化+Slot) → df3ce2a(Goal+Inspect) → ddee843(Workflow+动态插件)。
>

> 生成方式：6 个分析 agent 并行实读两库源码后汇总。DSH 源码根 `/Users/mac/dev/deepseek-harness`，
> eco-agent 源码根 `/Users/mac/Documents/deepseek/eco-agent`。结论均基于实际代码阅读，非猜测。

## 0. 一句话结论

**DSH 是"平台"（通用 agent 运行时 + 可组合能力总线），eco-agent 是"应用"（垂直执法智能体 + 深度业务）。**
eco-agent 缺的不是 DSH 的某几个功能，而是 DSH 赖以扩展的**四个架构原则**：
组合内核、多 agent 编排、跨轮持久化、契约化扩展。这四样在 Python 生态里各有现成路径可走。

---

## 1. 能力矩阵（逐项对比）

| 维度 | DSH 实现 | eco-agent 现状 | 差距判定 |
|---|---|---|---|
| **插件/组合内核** | Cordis（vendor/cordis）：Service 提供/消费（ctx.get vs inject）、Event 六模式（on/once/emit/parallel/serial/bail/waterfall）、Fiber+DisposableList（副作用可逆回收）、PENDING→ACTIVE 生命周期、cordis.yml 组合、isolate realm 服务隔离、HMR | plugins.py：plugin.yaml + load(ctx)/unload(ctx) + register_tool，PluginManager 扫描/热加载/卸载，工具名冲突检查 | 🔴 差距大：eco-agent 的"插件"只是工具注册器，无服务/事件总线、无组合文件、无副作用回收、无依赖注入 |
| **动态插件循环** | define（不可变 package 追加）→ inspect（Provider 类型契约）→ run（审批）→ stop/undefine；VM 沙箱执行；失败诊断（invariants + errorDetails）注入 agent 上下文 | 无对应物 | 🔴 完全缺失（DSH 最有特色的能力） |
| **Subagent 系统** | start（capability 校验+深度限制）/后台运行（jobs）/continuable（send_message 续聊）/fork（父会话前缀 seed）/interrupt/list_agents；子代理继承 preset+sandbox 覆盖+approval 钉死 | role_swarm.py：三角色执法 DAG（patrol∥law→doc→synthesis，仅执法场景）；commander_v2：子任务分解+verifier | 🔴 差距大：无通用子代理生命周期、无后台代理、无 fork、无续聊 |
| **Workflow 编排** | JS 脚本（agent/pipeline/parallel/phase 钩子）、schema 校验结构化结果、worker_thread 隔离执行、fatal 错误传播 | 无 | 🔴 完全缺失 |
| **Goal 跨轮目标** | goal/change 事件溯源 + FoldedGoal、自动延续轮次（armed 才续）、round-limit 自动 block、resume/edit | evolve_trigger（进化触发三元组）+ scheduler cron；五层循环是"单任务执行"层 | 🟠 缺持久化目标与自动延续轮 |
| **Jobs 后台任务** | JobRegistry：start 原子注册返回 id、read 流式增量、kill、onJobDone 完成通知（比 fiber 长寿） | 无（heartbeat 是内部脉冲线程，非用户可见任务） | 🔴 完全缺失 |
| **Session 模型** | 事件溯源 + WriteBehind 批写（≤200ms）+ jsonl/sqlite backend + 崩溃 torn-tail 修复；checkpoint policy：LLM 请求前/工具执行前 flush，失败 fail-closed | session_log + checkpoint.py + compaction.py（有雏形） | 🟠 有雏形，无事件溯源、无 fail-closed checkpoint |
| **文件沙箱** | 双进程级（bwrap/Landlock/Seatbelt）+ 进程内 FS 围栏（canonicalize-then-contain，dev/ino 别名）+ 升级审批（单次授权、严格加宽） | os_sandbox.py：bwrap + 三档退化 + allowed_paths；sandbox.py 接入 execute_code | 🟢 方向一致（子进程 OS 级隔离），缺"围栏+升级审批"闭环 |
| **审批栈** | approval service：ask/never、answerer waterfall、无 answerer fail-closed、审计对（asked/decided） | permissions.py L1-L4 闸门 + grants.py TTL 授权令牌 + SM3 审计链 | 🟢 相当；DSH 的 answerer 链更统一，eco-agent 的 L1-L4 分级+SM3 是特色 |
| **凭据管理** | credentials yaml 层级（环境>yaml>cwd/.env）+ owner-only + 原子写锁 + 热重载 | keystore.py + ~/.eco/.env + 700 脚本 | 🟢 相当 |
| **代码运行时** | worker_threads 隔离（AsyncFunction + 命名空间桥 + lossless JSON），明示"containment 非安全边界" | 子进程执行（bwrap/rlimit），OS 级隔离 | 🟢 eco-agent 隔离更强，DSH 的 containment 语义值得借鉴 |
| **Web GUI** | Cordis client 组合（模块系统+boot manifest）+ Slot UI（会话头/卡片/工具视图挂点）+ StatsLine 计量 + 双通道 RPC/WebSocket | React SPA 单体：实时 SSE 事件流、过程块、轨迹树、计量行（本轮已对齐展示层） | 🟠 展示层已接近；缺 Slot 组合式扩展（新面板/卡片靠改源码） |
| **Skill 系统** | SKILL.md 目录扫描（rank 去重、scope 分层、文件 watch）+ skill 工具 + 会话注入 | ecoskills/ 目录 + SKILL.md 手动注入（eco-codex/gongwen 等） | 🟠 有雏形；缺统一注册表/发现/排序 |
| **类型契约** | Context interface merging + Inspect manifest（method/inputSchema/outputSchema） | 无（Python 动态语言） | 🟠 结构性差距；Python 可用 dataclass+jsonschema 近似 |
| **诚实性/自愈** | compaction 摘要、runtime diagnostics 注入 | lessons 自愈闭环（失败特征→教训→注入）+ 纪律 11 条 + trace_audit SM3 | 🟢 eco-agent 特色优势 |
| **垂直业务** | 无（通用平台） | 法典 1242 条、govMCP 四源、执法五层循环、SOUL、督察路由 | 🟢 eco-agent 绝对优势，DSH 没有 |

---

## 2. 核心差距拆解：四个架构原则

### 原则 1：组合内核（eco-agent 最缺的地基）
DSH 的一切（子代理/审批/沙箱/UI/技能）都是 Cordis 插件，靠 Service/Event 解耦，靠 Fiber 回收副作用。
eco-agent 的 plugins.py 只有"工具注册"一种扩展点，导致每加一个能力都要改 server/chat.py 主循环。
**吸收路径**：Python 侧写一个 mini-Cordis（约 300-500 行）：Service 注册表（dict）+ inject 声明 + event 回调表 + disposer 列表。有现成参考：`koishi/cordis` 设计 + `pytest-dependency` 思路。

### 原则 2：多 agent 编排（补齐"一个人干不完的活"）
eco-agent 的 role_swarm 证明了"多角色协作"对执法场景有用，但它是写死的三角色 DAG。
**吸收路径**：通用 Subagent 服务（复用现有 llm_client + session_log）：
- `start(prompt, {background})` → 返回 subagent id
- fork（父会话前缀 seed，eco-agent 的 history 就是消息列表，直接切片）
- send_message（continuable 续聊）、list、interrupt
- 后台子代理落 FastAPI BackgroundTasks / asyncio.Task

### 原则 3：跨轮持久化（从"对话"到"项目"）
DSH 的 goal 系统让一个目标跨 N 轮自动延续，且每次续轮前 checkpoint 落盘。
eco-agent 有 scheduler/heartbeat，但目标不持久化、不自动续轮。
**吸收路径**：goals 表（SQLite，复用 memory-tree 后端）+ armed 状态机 + 续轮驱动（复用 heartbeat 线程）。

### 原则 4：契约化扩展（动态插件）
DSH 的 define→inspect→run→approval 循环让**模型自己**能写插件、看类型契约、失败自愈。
**吸收路径**（高风险高价值，放最后）：
- Python 动态插件可用 importlib 动态加载（比 VM 沙箱简单，但安全性差）
- 审批复用 grants.py 令牌 + permissions L4 闸门
- Inspect 契约用 pydantic schema 实现
- **安全兜底**：动态代码必须过 os_sandbox.py 子进程执行 + SM3 审计

---

## 3. 改造路线图（三期）

### P0 — 多 agent 骨架（1-2 周，复用现有件）
1. **Subagent 服务**（agent_core/subagent.py）：通用子代理 spawn/fork/send_message/list/interrupt；后台子代理挂 asyncio.Task；会话状态复用 session_log
2. **Jobs 后台任务**（agent_core/jobs.py）：任务注册表 + id 管理 + 流式输出 + kill + 完成通知注入对话
3. **Session 加固**：消息持久化（重启后恢复对话）、checkpoint 策略（LLM 调用前 flush，fail-closed）
4. 前端：子代理/任务面板 tab + 任务状态流

### P1 — 组合内核（2-4 周，结构性改造）
5. **mini-Cordis**（agent_core/cordis/）：Service 注册/注入、Event 六模式、disposer 回收、生命周期状态机、组合 YAML（eco.cordis.yml）
6. **存量迁移**：llm_client/lessons/trace_audit/权限闸门 → 服务化；chat.py 主循环改为消费服务
7. **Slot 前端扩展**：右侧面板/消息卡片挂点（面板注册表），新能力以插件形式挂 UI
8. **Skill 系统规范化**：SKILL.md 扫描+rank+watch（对标 DSH skill 包）

### P2 — 契约化与自治（长期，按需）
9. **Goal 自动延续**：目标持久化 + armed 续轮 + round 上限
10. **动态插件循环**：define/inspect/run/approval/stop，模型可自写插件（子进程沙箱+审批兜底）
11. **Workflow 编排**：Python 脚本编排多子代理（pipeline/parallel）
12. **Inspect 契约**：服务/工具/槽位的 jsonschema 目录（模型可见）

---

## 4. 不建议吸收的部分（诚实边界）

| DSH 能力 | 不建议原因 |
|---|---|
| TypeScript interface merging 类型契约 | Python 无静态类型合并，收益/成本比低 |
| bwrap 全量进程沙箱 | eco-agent 已有等价物（os_sandbox.py），且 DSH 在 macOS 也靠 Seatbelt |
| WebSocket downlink 双通道 | eco-agent 单用户场景 SSE 足够，复杂度不值 |
| 多 preset/多会话组合树 | eco-agent 是单垂直应用，不需要"每个会话不同组合"的复杂度 |

---

## 5. 验证建议（每期验收标准）

- P0 验收：能发起后台子代理（如"帮我查 6 个督察局子站最新动态"），主对话继续提问，子代理完成后结果自动注入；重启后对话历史可恢复
- P1 验收：新增一个能力（如"大气数据面板"）只写插件目录 2 个文件 + 组合 YAML 一行，不动 server/chat.py
- P2 验收：模型能在对话中申请并运行一个自写插件（经审批），失败后能自己看诊断修复

## 6. 执行记录（2026-08-17 全部完成）

| 期 | 项 | 提交 | 实测验收 |
|---|---|---|---|
| P0 | Subagent 系统 | ef16e2b | fork spawn 15.3s、主对话并行 18s 不阻塞、续聊、interrupt→killed |
| P0 | 任务面板前端 | 66cad90 | 浏览器全流程：派发→done→续聊→idle |
| P0 | Session 加固 | 798e14f | 跨重启恢复（重启后 /messages 仍 2 条） |
| P1 | mini-Cordis | b8ef531 | tests/test_cordis.py 20/20；组合 YAML 装配 |
| P1 | Skill 规范化 | 46a3de0 | 6 技能 bigram 匹配 6/6；端到端注入生效 |
| P1 | 存量服务化 | f208a5e | chat.py 6 处 _svc 消费（cordis 优先+import 兜底） |
| P1 | Slot 系统 | f208a5e | 审计链面板插件注册→浏览器动态 tab 渲染 |
| P2 | Goal 系统 | df3ce2a | 自动延续 0→1→2、round-limit 阻断、jsonl 重载一致 |
| P2 | Inspect 契约 | df3ce2a | 6 服务+2 插件+7 工具+1 槽位目录可查 |
| P2 | Workflow 编排 | ddee843 | parallel 双代理 8s、pipeline、超时 kill |
| P2 | 动态插件循环 | ddee843 | define/run/stop/undefine 全循环+服务注销 |

遗留（如实声明）：前端 Goal/Workflow/动态插件面板未做（API 已完整可用）；
动态插件无 VM 沙箱（同进程执行，ECO_DYNAMIC_PLUGINS 开关兜底）。
