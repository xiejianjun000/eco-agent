# ECO AGENT — 核心记忆

> **跨会话持久化核心记忆，每次会话自动加载**

---

## 项目状态

- **当前版本**：v1.0.0（DSH 对齐版）
- **当前阶段**：生态环境垂直领域全能 AI Agent（对标 DeepSeek Harness）
- **项目根目录**：`/Users/mac/Documents/deepseek/eco-agent`
- **知识库**：FlowWiki Obsidian Vault + EHS 知识库（81,071 篇）+ 环评知识库（eia MCP）

## 核心宪法

- **CLAUDE.md**：主 Agent 宪法（身份 + 职责 + 启动协议）
- **SCHEMA.md**：知识宪法（14 维质量标准 + ACE 三阶段审查 + 操作纪律）
- **G 方法论**：Git-based Development Governance（8 大原则）

## 已安装的工具（真实接线清单）

**聊天通道（11 内置 + 28 政务平台）**：statute_lookup / statute_search /
kb_search / kb_semantic_search / execute_code / web_fetch / query_air_quality /
save_document / analyze_document / generate_pptx / calculate_carbon_emission /
hunan_case_list；政务平台三组（govmcp 格式，L1 只读 + SM3 审计）：
- wryzxjc_*（8）：娄底市污染源在线监测——污染源/预警报警/设备/实时/历史数据
- sthjzf_*（11）：国家四平台——规范涉企检查/行政处罚案件/水环境任务台账
- permit_*（9）：排污许可管理平台——许可证库/企业库/执行情况/停产/档案

**MCP 挂载**：
- eia（环评审查知识库）：kb_search / kb_verify / kb_calculate / kb_industry_info（L1 只读）
- github（官方 GitHub MCP）：仓库检索/读文件/提交/Issue（L1 只读；写操作走权限确认；
  需在 .env 配置 `GITHUB_PERSONAL_ACCESS_TOKEN`）
- ehs_kb（执法知识库 SSE）：kb_search / kb_semantic_search 等（L1 只读）

**govmcp 政务工具注册表（/api/v1/tools，139 工具）**：三平台全量
（在线监测 11 / 国家四平台 17 / 排污许可 11，其中水环境线索核实/确认
approval_required + confirm 双闸 + L4）。凭证走 .env：STHJZF_*（431381 已实测
登录成功）、WRYZXJC_*（待补）、PERMIT_*（内网，待填）。

**平台能力（对标 DSH）**：子代理（目录/发起/续聊/中断）、跨轮目标、工作流编排
（agent/pipeline/parallel）、动态插件（define/run/stop/undefine）、插槽面板、
L1-L4 权限闸门 + SM3 审计链、事件溯源会话（断尾修复 + fail-closed checkpoint）、
**DSH 式模块化提示词组装**（片段注册表 + /prompt 管理 API + 人设切换 + 建议气泡）

**联网白名单**：gov.cn / mee.gov.cn / github.com / gitee.com / epmap.org 等
（`ECO_WEB_ALLOW_ALL=1` 可放开）

## 重要的路径

| 路径 | 用途 |
|:-----|:------|
| `_scripts/` | 自动化工具脚本（tool_wiring.py 接线治理报告等） |
| `ecoskills/` | 执法 + 环评审查技能（eco-codex/fagui-query/eia-review/...） |
| `govmcp/` | MCP 服务器（eia-mcp-server、github-mcp-server） |
| `profiles/eco-agent/` | 配置（config.yaml/SOUL.md/PERMISSION.md/本文件） |
| `memory-tree/` | Memory Tree 数据目录 |
| `docs/` | 724 验证方案 / DSH 对齐清单 / 挂载档案 |

## 当前任务

- DSH 对齐 v1.0 已完成（11 轮 UI 对齐 + 核心能力补齐，验收报告见 docs/dsh-alignment-acceptance.md）
- GitHub MCP 已挂载，待用户配置 `GITHUB_PERSONAL_ACCESS_TOKEN` 后全功能生效

### 启动命令

```bash
cd /Users/mac/Documents/deepseek/eco-agent
ECO_DYNAMIC_PLUGINS=1 python3 -m eco.cli server --port 8321   # 管理 API + Web GUI
```
