# 政务平台三 MCP · govmcp 格式转换挂载档案

> 日期：2026-08-22 · 目标 goal-b16c63d8 · 已全部完成并实测

军哥要求：把私人仓库里的三个 MCP 按 govmcp 格式修改后挂载到 eco-agent 下面。

## 一、来源（xiejianjun000 私人仓库，gh API tarball 拉取）

| 仓库 | 平台 | 转换产物 |
|:-----|:-----|:---------|
| `eco-wryzxjc-mcp` | 娄底市污染源在线监测系统（重点污染源自动监控，博安达）218.77.102.213:12369 | `govmcp_tools/wryzxjc.py`（11 工具） |
| `eco-sthjzf-mcp` | 国家生态环境保护综合执法监管平台（四平台）统一 CAS sthjzf.lem.org.cn:8090 | `govmcp_tools/sthjzf.py`（17 工具） |
| `permit-management-mcp` | 全国排污许可证管理信息平台-管理端（内网） | `govmcp_tools/permit_management.py`（11 工具） |

原仓库为旧版 MCP Server（stdio，`mcp.server.mcpserver.MCPServer` + JSON 字符串返回），
已全部改写为 govmcp 框架标准形态：

- `@govmcp_tool(name, description, category, tags, approval_required)` 装饰器 + 类型注解自动推断 input_schema
- 返回结构化 dict（registry.call_tool 统一序列化）
- 工具名加平台前缀防注册表冲突（wryzxjc_ / sthjzf_ / permit_）
- 会话持久化从"脚本旁 session_state.json"迁移到 `ECO_DIR/sessions/`（无写权限自动降级纯内存）

## 二、挂载接线（eco-agent 三层）

1. **govmcp 注册表**：`govmcp_tools/__init__.py` register_all 注册三模块 →
   `/api/v1/tools` 可见（总数 139，新分类 执法平台-污染源在线监测/国家四平台/排污许可管理）。
2. **聊天通道**：`server/api/chat.py` `_ensure_platform_tools()` →
   `register_external_tool(risk_level=L1)` 把 28 个只读工具注册进
   `tools_registry`（LLM 定义表 + `_HANDLERS` + 风险覆盖）→ `_codex_tools()`
   合并进聊天工具表 → `_run_tool` 分发经 `execute_tool`（L1-L4 权限闸门 +
   SM3 审计链）。共 8 + 11 + 9 = 28 个聊天工具。
3. **治理**：`wiring_manifest.py` WIRED_REQUIRED +28；`PERMISSION.md`
   tool_risk_overrides +28（L1）+ 写工具 2 条（L4）；`.env` 增三组凭证变量。

## 三、安全设计（政务平台红线）

- **只读为主**：聊天通道仅暴露查询工具；登录工具不进聊天表（凭证不进聊天参数），
  由 `.env` 环境变量自动登录。
- **写操作双闸**：水环境线索核实/确认 `approval_required=True`（govmcp 元数据）
  + `confirm=true` 参数闸门 + PERMISSION.md L4 人工审批，三重保险。
- **通用 raw 接口**（wryzxjc_raw_query / sthjzf_water_api）仅在 govmcp 注册表可见，
  不进聊天工具表。
- **数据不出本机**：本机直连政务平台（非公网 API），全部决策写 SM3 审计链
  source=permission。

## 四、验证结果

| 项 | 结果 |
|:---|:-----|
| 单元/集成测试 `tests/modules/test_govmcp_platforms.py` | 19 项全过 |
| 全量 pytest | 100% 绿（1152 passed, 2 skipped） |
| lint（新文件） | 0 问题 |
| `/api/v1/tools/stats` | 139 工具，三平台分类齐全，approval_required=2 |
| **国家四平台实连** | 431381/<密码见 .env> CAS 登录成功（AES+验证码 OCR），三平台 token 全通 |
| **端到端聊天实测** | 模型自动调用 sthjzf_water_task_statistics/task_list/query_cases，返回冷水江真实执法数据：任务总计 4（待核实1/待确认2/已办结1）、线索 A202606170200（金富源碱业疑似篡改监测数据）、H202604290549（冷钢超总量排污，已办结不属实）；行政处罚全国库 1363 条 |
| 在线监测平台 | 网络可达（218.77.102.213:12369），登录凭证未知 → `.env` WRYZXJC_* 待军哥补 |
| 排污许可平台 | 内网系统 → `.env` PERMIT_BASE/JGZF_BASE/KEY 待内网环境下补 |

## 五、遗留

1. `WRYZXJC_USERNAME/PASSWORD`：在线监测平台冷水江辖区账号（试过 431381/<密码见 .env> 不通用），军哥补进 `.env` 即自动生效。
2. `PERMIT_*`：排污许可管理端内网地址 + 账号密码 + 实施监管系统签名密钥。
3. 行政处罚案件列表接口返回全国默认租户数据，按冷水江筛选需先走部门树
   （sthjzf_list_depts parent_id 逐级下钻）或案号前缀——下一步打磨点。
