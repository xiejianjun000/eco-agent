# eco-agent × DSH 穿透式差距审计（2026-08-21 实测）

> 方法：逐项真实调用 eco-agent 服务（API/execute_tool/聊天/代码路径），与 DSH 运行时对照。
> 判定：✅ 对齐 · 🟠 部分/有实现但未接线或退化 · ❌ 缺失。
> 每项附实测证据，无证据不写结论。

## 1. 核心循环与工具

| # | 能力 | 判定 | 证据 |
|---|------|------|------|
| 1.1 | 聊天（工具循环） | ✅ | /chat 真实调用 statute_lookup/execute_code/mcp__github__* 返回真实数据 |
| 1.2 | SSE 流式 + think/tool 轨迹 | ✅ | streamChat 实测；v4-pro reasoning_content → think 事件 |
| 1.3 | 工具接线治理 | ✅ | wiring_manifest + 报告 + 回归测试；聊天可见 23 工具 |
| 1.4 | 模型路由/降级 | ✅ | deepseek-chat 默认 + v4-pro/reasoner 可选；401/429/402 failover 链 |
| 1.5 | 权限闸门 L1-L4 | ✅ | 全单测覆盖；execute_code 沙箱放行/command 拦截实测 |
| 1.6 | 沙箱执行 | ✅ | Docker→bwrap→本地三级降级实测；**隔离强于 DSH**（子进程 vs worker_threads） |

## 2. 会话与持久化

| # | 能力 | 判定 | 证据 |
|---|------|------|------|
| 2.1 | 会话事件链 + 恢复 | ✅ | session_log SHA-256 链 + /sessions/{id}/messages 重放（53 条实测） |
| 2.2 | 断尾修复 | ✅ | repair_torn_tail 5 测试全绿 |
| 2.3 | fail-closed checkpoint | ✅ | LLM 请求前 guard 接线 + 中部损坏阻断测试 |
| 2.4 | DSH 式事件溯源（WriteBehind/快照） | ✅ | **已修复（并行组 A）**：append_buffered/flush 批写 + 可选防抖定时 + durable() 先冲刷；每轮 2 fsync→1 |
| 2.5 | 崩溃 torn-tail 修复 vs 全事件溯源 | 🟠 | 有修复，但无 seq+WriteBehind 批写与 fail-closed flush 策略 |

## 3. 平台能力（DSH 三件套 + 扩展）

| # | 能力 | 判定 | 证据 |
|---|------|------|------|
| 3.1 | 子代理 | ✅ | 目录/发起/续聊/中断/输出流；实测真实任务完成 |
| 3.2 | 跨轮目标 | ✅ | 创建/暂停/恢复/轮次上限；jsonl 持久化 |
| 3.3 | 工作流编排 | ✅ | agent/pipeline/parallel 实测（DAG 4 代理 58s） |
| 3.4 | 动态插件循环 | ✅ | define/run/stop/undefine 全循环 UI+API 双实测 |
| 3.5 | Inspect 契约目录 | ✅ | /inspect/list + query(name=...) 实测 |
| 3.6 | Slots | ✅ | 注册 + 数据 + 前端动态 side.tab + 审计链结构化渲染 |
| 3.7 | MCP 挂载 | ✅ | github 27 工具 + eia 4 工具注册并穿透调用；聊天可见 |
| 3.8 | 插件市场 | 🟠 | PluginMarket 类存在，未见挂载/前端 |
| 3.9 | 审批栈（answerer 链） | ✅ | **已修复（并行组 C）**：ApprovalService（ask/never + answerer 瀑布 fail-closed + asked/decided 审计对 + jsonl 持久化）+ /approvals API + L4 接线；web 交互审批 UI 仍待前端 |

## 4. 记忆 / 技能 / 知识

| # | 能力 | 判定 | 证据 |
|---|------|------|------|
| 4.1 | 记忆树 | 🟠 | sqlite 持久化存在，但 0 节点——运行时从未产出（verify_ops 实测） |
| 4.2 | 技能系统 | ✅ | ecoskills 5 个 + 会话注入（skill_dir match）；**修复了 /skills 500（越界 mkdir 无兜底）** |
| 4.3 | 进化/心跳/调度/自愈 | ✅ | **已修复（并行组 D）**：smoke 实测 116 心跳+2 进化+版本化报告真实落盘；heartbeat 尊重 ECO_DIR；另修 meta_evolution 版本号排序与 verify_ops 口径 |
| 4.4 | 观测 span 树 | ✅ | **已修复（并行组 B）**：SpanTree 尊重 ECO_DIR+降级；8 处 LLM 调用与工具执行全包 span；测试覆盖 |

## 5. 安全与合规

| # | 能力 | 判定 | 证据 |
|---|------|------|------|
| 5.1 | SM3 审计链 | ✅ | 671 条链完整可验证（audit-panel 实测） |
| 5.2 | 凭据管理 | ✅ | .env + keystore + envboot（两级合入）；gitignore 保护 |
| 5.3 | 文件沙箱升级审批 | 🟠 | 沙箱隔离有；**无 DSH 式"单次授权、严格加宽"升级流程** |
| 5.4 | 等保三级要素 | 🟠 | SM3+分级+审计齐；等保测评文档未产出 |

## 6. Web UI（DSH 30 ui-* 包对照）

- ✅ 已对齐 26 项（见 docs/dsh-ui-alignment.md 矩阵，11 轮逐项实测）
- ⏳ 环境限制 4 项：图片附件（视觉模型——账户已有 deepseek-v4-flash-vision-exp，可接）、
  本地目录选择器、命令面板、ui-primitives

## 7. 本轮修复（审计中当场修掉的）

1. **/skills 500**：SkillRegistry 越界 mkdir 无兜底 → 尊重 ECO_DIR + mkdir/保存失败降级内存态（实测 200）
2. **envboot 测试污染**：进程级 .env 引导在 pytest 下跳过（单测 100% 恢复）
3. **观测 span 未接线**：列为下一项待修（chat.py 接 SpanTree，成本低）

## 8. 结论：核心差距收敛为四类

| 类别 | 内容 | 建议 |
|------|------|------|
| A 事件溯源深度 | jsonl 全量读写 → 事件溯源+WriteBehind | 中期架构项 |
| B 观测接线 | 聊天循环接 SpanTree | 短期，下轮可修 |
| C 审批栈 | answerer waterfall + web 交互审批 | 中期 |
| D 后台循环证据 | 进化/心跳/记忆树在部署机长稳验证 | 部署后用 724 巡检方案验证 |
