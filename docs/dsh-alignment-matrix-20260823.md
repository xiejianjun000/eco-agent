# eco-agent ↔ DSH 功能/架构对齐矩阵

> 日期：2026-08-23 · 依据：本会话全量建设 + 三测套件（冒烟/穿透/压力）实测
> 验证入口：`python3 _scripts/smoke_test.py [--llm]`（33 项检查）

## 一、核心架构对齐

| DSH 架构要素 | eco-agent 实现 | 状态 | 证据 |
|-------------|---------------|------|------|
| Cordis 插件内核 | agent_core/cordis（服务注册/插件行） | ✅ | cordis 上下文装配日志（6 服务+2 插件） |
| 事件溯源会话 | session_log.py（SHA-256 链 + WriteBehind + 断尾修复） | ✅ | smoke_test 会话创建 + audit_tail/session_log_tail 工具 |
| 权限闸门 L1-L4 | permissions.py + PERMISSION.md 覆盖表 | ✅ | 79 项覆盖，L1 自动/L3 白名单/L4 审批 |
| SM3 审计链 | prompt_engine PromptAuditChain（可验证） | ✅ | 205 条完整可验证（体检+冒烟双检） |
| 动态插件 | define/run/stop/undefine + 插槽面板 | ✅ | /api/v1/slots + dynamic-plugins 路由 |
| 子代理/后台任务 | subagent + goals（自动续轮）+ 事件通知 | ✅ | spawn_goal 实测 armed 启动 + /goals/events |
| 工作流编排 | agent/pipeline/parallel | ✅ | workflow 路由（既有） |
| 提示词组装（一切皆插件） | prompt_sections 注册表 + 动态片段 + 注入 API | ✅ | /api/v1/prompt/overview，规则 13-18 |
| 建议提示词 | suggest.py + Web 气泡 | ✅ | 实测 3 条建议 |
| 人设/阶段切换 | switch_persona + PhaseStateMachine | ✅ | 三阶段实测切换 |

## 二、工具层对齐

| DSH 能力 | eco-agent 工具 | 状态 |
|---------|---------------|------|
| Shell 执行 | shell_run（白名单+审计） | ✅ |
| 文件读写编辑 | file_read/write/edit（根内校验+唯一命中） | ✅ |
| 网页读取/搜索 | web_fetch + web_search（多引擎） | ✅ |
| 浏览器打开 | open_url（白名单） | ✅ |
| 沙箱代码 | execute_code（L3 三层隔离） | ✅ |
| 知识检索 | statute_*（法典 1242 条）+ kb_* + 条文关系图谱 | ✅ |
| 政务平台直连 | 三平台 govmcp（39 工具）+ 腾讯文档 243 MCP | ✅（2/3 平台凭证已通） |
| 环境公开数据 | 地表水自动站 + 空气质量预报（实测端点） | ✅ |
| 长任务目标 | spawn_goal + 自动续轮 | ✅ |
| 审计回溯 | audit_tail + session_log_tail | ✅ |

## 三、行为层对齐（穿透探针实测）

| 探针 | 结果 |
|------|------|
| 注入抗性（红线拒绝） | ✅ 坚定拒绝+法律后果 |
| 法规时效先查后答 | ✅ file_read+web_search+statute_search |
| 能力自证（不甩锅"未挂载"） | ✅ 直查腾讯文档空间 |
| 执行层工具直调 | ✅ shell_run 真实调用 |
| 三角色协作 | ✅ swarm_patrol/law/doc（含法条自动核验） |
| 幻觉格式净化 | ✅ 平衡块删除+截断 |

## 四、质量与评测对齐

| 项 | 结果 |
|----|------|
| 接线一致性（注册必有 handler） | ✅ 自动化测试 |
| 评测机械门禁（引用真实性，虚构法条必挂） | ✅ 35/35 |
| 技能全库自审（10 项评分卡） | ✅ 18/18 ≥70 |
| evals 45 题基线 | ✅ overall 81.2%（注入抗性 44.4% 已加确定性警示） |
| 三测套件（冒烟/穿透/压力） | ✅ 33/33 |

## 五、已知差距（如实）

| 项 | 说明 |
|----|------|
| Playwright 浏览器自动化 | 未装（API 通道已覆盖业务场景，按需再加） |
| .dsh 插件包格式适配 | 未做（提示词片段注册表已对齐语义） |
| 45 题基线注入抗性 | 44.4% 最弱项，警示已加，待复测验证 |
| 排污许可/国控平台 | 内网不可达，凭证已就位待内网环境 |
| 市控平台（wryzxjc） | 公网可达，待军哥补账号密码 |
