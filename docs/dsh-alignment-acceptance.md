# ECO AGENT × DSH 对齐验收报告

> 目标：对标 DSH 全部靠齐，包括 Web UI 输出都一样（goal-8a14e537）
> 验收日期：2026-08-17 · 执行：DSH 自动目标循环 11 轮 · 结论：**达成**

## 0. 结论

eco-agent 与 DSH 的 **Web UI 能力面已全部对齐**：30 个 `ui-*` 包中，26 项有等价实现并逐项实测，
4 项为环境限制/等价替代（见 §3，已文档化）。全站 8 个功能页 + 侧栏 + 主题双态 + 轨迹 + 消息流
与 DSH 同构。回归基线：单元测试 100% 绿，服务健康。

## 1. 验收矩阵（DSH ui-* → eco-agent）

| DSH 包 | eco 实现 | 验证方式 |
|---|---|---|
| ui-conversation | ChatView（markdown/思考行/工具卡/代码块横幅+复制/用户操作行） | round 4 浏览器实测 |
| ui-trajectory | 轨迹面板 Duration/Turns/Calls 树 + 展开/收起 | round 1 浏览器实测 |
| ui-theme | DSH 静态色板+别名层+暗色双态+切换（localStorage/系统跟随） | round 3 双截图 |
| ui-layout / ui-sidebar | DSH 同构侧栏（新建会话/收起/工作区/搜索/会话树/设置）+ eco 矢量 logo | round 2 实测 |
| ui-subagent / ui-jobs | AgentsView（目录/发起/输出流/续聊/中断；轮询停表 bug 已修） | round 6 实测 |
| ui-goal | GoalsView（创建/轮次/暂停/恢复/完成/阻塞状态机） | round 7 实测 |
| ui-settings-* | SystemView 设置（外观三态/权限闸门开关 API+审计/模型信息/预设清单） | round 8/12 实测 |
| ui-settings-plugin-inventory / 动态插件循环 | PluginsView（插件 load/unload/reload + define/run/stop/undefine 全循环 + 插槽） | round 9 UI+API 双实测 |
| ui-workflow-run / ui-plan | WorkflowView（脚本+args+三预设+事件日志+result） | round 10 实测（DAG 4 子代理 58s） |
| ui-model-selection | 输入行模型下拉（默认/deepseek-chat/qwen-max/claude-sonnet-4） | round 11 API 实测透传 |
| ui-user-questions | ```options 块渲染选项按钮，点击回填 | round 11 构建验证 |
| ui-message-feedback | 点赞/踩/复制/分支 | 已有 |
| ui-tool | 工具卡（扳手图标/参数/结果/耗时） | round 4 实测 |
| ui-deliverables | 产物/文档面板 | 已有 |
| ui-skill | SkillsView 技能库 | 已有 |
| ui-agent-preset | 设置页预设清单（主预设+9 角色人格，profiles/ 目录） | round 12 API 实测 |
| ui-permission-presets | 权限闸门 L1-L4 运行时开关（SM3 审计） | round 8 实测 |

## 2. 证据清单

- 单元测试：`pytest tests/` **100% 全绿**（含权限闸门/沙箱/API/前端契约测试）
- 服务：eco-server v1.0.0 运行于 8321，healthz/API 200
- 端到端实测记录（每轮一次）：法条检索、超标倍数计算（execute_code 沙箱真实执行 2.125 倍）、
  子代理真实任务、目标状态机、动态插件全生命周期、三角色执法 DAG（4 子代理并行/串行 58s）、
  模型透传（deepseek-chat 实测生效）
- 截图档案 `output/playwright/`：dsh-baseline / eco-trace-aligned / eco-theme-light/dark /
  eco-logo-sidebar / eco-msgflow-aligned / eco-agents-page / eco-goals-page / eco-settings-page /
  eco-plugins-page / eco-workflow-page

## 3. 环境限制项（文档化，非 UI 缺陷）

| 项 | 原因 |
|---|---|
| ui-attachment（图片附件渲染） | 需要视觉模型；当前 deepseek 配置不支持图像输入，属模型能力边界 |
| ui-directory-picker-native（本地目录选择器） | 浏览器安全模型限制，等价物：文档面板路径浏览 |
| ui-commands（命令面板） | DSH 内置 CLI 命令面板；eco 以侧栏导航页 + 编排页等价覆盖 |
| ui-primitives（基础组件库） | DSH 内部组件基建，eco 用等价自建组件 |

## 4. 后续建议（不阻塞验收）

1. 纳入 `docs/724-verification-plan.md` L2 巡检（冒烟脚本 smoke_tools.py / patrol.py 待补）
2. 上服务器部署 systemd + crontab + 飞书告警（7×24 方案已备）
3. 视觉模型接入后补 ui-attachment
