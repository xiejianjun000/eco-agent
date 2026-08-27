# DSH 环评审查与排污许可证技术审查插件

> 全国通用环评技术审查DSH插件，支持国家通用规则（保底85%）+ 省级规则热插拔 + MCP知识库增强（冲击95%）。

## 功能特性

- **国家通用规则引擎**：基于76件国家/部委文件，20条核心审查规则
- **省级规则热插拔**：浙江/江苏/广东等省份规则包即插即用
- **MCP知识库增强**：集成EHS知识库（**81,071篇文档**），向量检索 + 混合排序 + LLM二次验证
- **双面插件架构**：宿主侧审查 + 浏览器侧可视化

## EHS 知识库 MCP 配置

### 服务端点
- **类型**：SSE（Server-Sent Events）
- **URL**：`http://111.230.89.107:8000/sse/`
- **鉴权**：`X-API-Key`（通过环境变量注入）
- **文档规模**：**81,071 篇**（向量搜索已启用）

### 环境变量设置
```bash
export EHS_KB_API_KEY="your-api-key"
```

### 安装

```bash
# 本地开发
dsh plugin --profile web add ./dsh-eia-review-plugin

# 从npm（发布后）
dsh plugin --profile web add dsh-eia-review-plugin
```

## 配置

编辑 `cordis.patch.yml`：

```yaml
- insert:
    - id: eia-review
      name: 'dsh-eia-review-plugin'
      config:
        province: "zhejiang"      # 默认省份
        reviewMode: "both"        # eia | permit | both
        enableMCP: true
        strictMode: true
```

## 使用

在DSH Web UI中：

```
请对上传的环评报告进行技术审查
```

或调用工具：

```typescript
ctx.tools.call("eia_technical_review", {
  reportPath: "/path/to/report.pdf",
  reportType: "report_book",
  projectProvince: "zhejiang",
  industry: "C26-化学原料和化学制品制造业"
})
```

## 准确率保障

| 层级 | 机制 | 准确率 | 文档支撑 |
|------|------|--------|---------|
| 规则引擎 | 20条国家通用规则 | **≥85%** | 76件国家/部委文件 |
| 知识库增强 | EHS MCP向量检索 | **≥95%** | **81,071篇文档** |

## 目录结构

```
dsh-eia-review-plugin/
├── src/
│   ├── core/              # 国家通用规则引擎（20条规则）
│   ├── provinces/         # 省级规则包
│   │   ├── zhejiang/      # 浙江省规则（基于2026年汇编）
│   │   └── _template/     # 其他省份接入模板
│   ├── parsers/           # PDF/Word文档解析
│   ├── mcp/               # EHS知识库MCP客户端（SSE远程连接）
│   └── index.ts           # 插件入口
├── skills/                # Agent Skills
├── knowledge/             # 内置知识库
├── cordis.patch.yml       # DSH插件配置
└── preset.yml             # Agent预设
```


## AI 驱动自我优化迭代

插件具备 **AI 驱动的自我优化迭代能力**，每天凌晨 3:00 自动执行：

### 监控范围

| 监控目标 | 仓库 | 监控内容 |
|---------|------|---------|
| DSH 框架 | `deepseek-ai/deepseek-harness` | 新版本、API 变更 |
| Cordis 内核 | `deepseek-ai/cordis` | 服务框架更新 |
| MCP 协议 | `modelcontextprotocol/specification` | 协议规范变更 |
| MCP SDK | `modelcontextprotocol/python-sdk` | SDK 更新 |
| LangChain | `langchain-ai/langchain` | RAG/Agent 技术 |
| DeepSeek LLM | `deepseek-ai/deepseek-llm` | 模型能力升级 |

### 自动优化流程

```
每天凌晨 3:00
    │
    ▼
┌─────────────────┐
│  GitHub 监控    │ ← 检查 9+ 个 AI 仓库
│  (API + 缓存)   │
└────────┬────────┘
         │
    ┌────┴────┬────────────┬────────────┐
    ▼         ▼            ▼            ▼
 DSH版本    MCP协议      AI能力       依赖安全
 监控       变更检测     发展追踪      扫描
    │         │            │            │
    ▼         ▼            ▼            ▼
┌─────────────────────────────────────────┐
│         自我分析与优化建议生成           │
│  • 代码质量分析                          │
│  • 规则库时效性检查                      │
│  • 知识库同步 (81,071 篇)               │
│  • 性能瓶颈识别                          │
└─────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│      自动生成优化任务清单               │
│  • 版本升级建议                          │
│  • 协议适配方案                          │
│  • 代码重构建议                          │
│  • 规则更新提醒                          │
└─────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│      AI 自动优化执行（可选）             │
│  • 依赖安全漏洞自动修复                   │
│  • 配置自动更新                          │
│  • 生成 PR 草稿                          │
└─────────────────────────────────────────┘
```

### 配置方式

#### 方式一：Cron（本地/服务器）

```bash
# 1. 给脚本添加执行权限
chmod +x scripts/maintenance.sh
chmod +x scripts/auto-optimize.sh

# 2. 编辑 crontab
crontab -e

# 3. 添加（每天凌晨 3:00）
0 3 * * * cd /path/to/plugin && ./scripts/maintenance.sh >> logs/cron.log 2>&1
30 3 * * * cd /path/to/plugin && ./scripts/auto-optimize.sh >> logs/auto-optimize.log 2>&1
```

#### 方式二：GitHub Actions（推荐）

已内置 `.github/workflows/daily-maintenance.yml`，自动：
- 每天凌晨 3:00 UTC+8 触发
- 监控 GitHub AI 发展
- 上传维护日志
- 失败时自动创建 Issue

**需要配置的 Secrets：**
- `EHS_KB_API_KEY`：知识库 API Key
- `GITHUB_TOKEN`：自动创建 Issue（已内置）

### 生成的报告

维护后自动生成以下报告：

| 报告文件 | 内容 |
|---------|------|
| `.ai-reports/version-updates.md` | DSH/MCP 版本更新提醒 |
| `.ai-reports/mcp-protocol-updates.md` | MCP 协议变更分析 |
| `.ai-reports/ai-capability-tracker.md` | AI 能力发展追踪 |
| `.ai-reports/optimization-suggestions.md` | 代码优化建议 |
| `.ai-reports/auto-tasks-YYYYMMDD.md` | 自动生成的任务清单 |
| `logs/maintenance-report-YYYYMMDD.json` | 完整维护报告 |

### 查看维护状态

```bash
# 查看最新维护报告
cat .ai-reports/ai-capability-tracker.md

# 查看优化建议
cat .ai-reports/optimization-suggestions.md

# 查看维护日志
tail -f logs/maintenance-$(date +%Y%m%d).log
```

## 开发

```bash
pnpm install
pnpm run build
pnpm dsh web --patch ./cordis.patch.yml
```

## 许可证

MIT
