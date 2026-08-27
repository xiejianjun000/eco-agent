# 插件/MCP 挂载档案（2026-08-21）

> 来源：GitHub xiejianjun000 近两日（08-18）三仓库 · 测试修复后挂载进 eco-agent
> 测试证据：eco-dsh-plugins 39/39 运行时检查通过；eia 插件 tsc 0 错误；eia MCP stdio 冒烟 tools/list + tools/call 真实穿透

## 1. 三个仓库的处置

| 仓库 | 性质 | 处置 |
|---|---|---|
| awesome-dsh-plugin | DSH 插件精选列表（文档站） | 无代码，未挂载 |
| eco-dsh-plugins | eco-agent 能力的 TS 反移植（权限闸门/审计链/记忆树，for DSH） | 测试 39/39 通过；eco-agent 原生已具备，无需回挂 |
| dsh-eia-review-plugin | 环评/排污许可审查插件 + EHS 知识库 MCP | ✅ **已挂载**（见下） |

## 2. 挂载明细（eco-agent）

| 层 | 路径 | 内容 |
|---|---|---|
| 技能 | `ecoskills/eia-review/` | SKILL.md（环评审查专家）+ manifest.json + kb/（national-laws.json、industry-standards.json） |
| MCP 服务 | `govmcp/eia-mcp-server/` | 源码+dist（node_modules 经符号链接指向测试目录，部署机需 `npm install`） |
| MCP 注册 | `.env` `ECO_MCP_SERVERS` | `{"name":"eia","transport":"stdio","command":["node",".../dist/index.js"]}` |
| 权限 | `PERMISSION.md` | mcp__eia__×4 → L1 只读豁免 |
| 实测 | execute_tool | kb_industry_info / kb_search / kb_verify 真实穿透返回 ✅ |

## 3. 测试中修复的原始仓库 bug（12 处）

1. `new RegExp(\`...)` 反引号开、双引号关 ×2（模板串未闭合，全文件解析崩塌）
2. `new IndustryDB()/new HazardousWasteDB()` 静态类错误实例化 ×6 处
3. import 路径 `../../types` → `../types`
4. `const挂靠迹象` 缺空格
5. StandardInfo.status 联合缺 "unknown"
6. dsh-tools schema：`required: false` 非法（应省略）、对象缺 `additionalProperties` ×4 工具
7. ReviewIssue 缺 kbConfirmed/kbCitation/kbRegulation/kbSimilarCases
8. `validateRiskIdentification` 缺 industryCode 形参
9. 省级规则包 `zhejiang/rules` 缺失 → 占位（热插拔设计）
10. MCP SDK：`setRequestHandler("tools/call")` 需官方 CallToolRequestSchema；tools/list 需显式注册
11. VectorStore 无降级 → ChromaDB 掉线时优雅降级关键词模式
12. `ctx.skills` / `ctx.tools.call` → cordis 服务安全查找

## 4. 数据侧遗留（机制已通，数据待装载）

- eia MCP 知识图谱内置行业有限（如 C25 不在库）；
- 向量检索需部署机运行 ChromaDB（或启用 EHS 知识库 81,071 篇文档库）。
