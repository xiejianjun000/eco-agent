# ECO AGENT 终极架构方案：6 大 AI 框架深度梳理分析与融合设计

---

## 第一部分：6 大 AI 框架全景梳理

### 框架定位总览

| 框架 | 全称 | 开发者 | 定位 | 核心哲学 | 关键语言 | 发布 |
|------|------|--------|------|---------|---------|------|
| **OpenClaw** | OpenClaw | Peter Steinberger | 通用 AI Agent 框架 | "AI的USB" MCP标准 | TypeScript | 2025 |
| **Hermes Agent** | Hermes Agent | Nous Research | 自进化通用 Agent | 复合效应自改进闭环 | Python | 2026.02 |
| **CLAUDE** | FlowWiki 主 Agent | xiejianjun000 | 法规知识库 | 知识宪法 14维质量+ACE | Markdown | 2026 |
| **CODEX** | FlowWiki Codex Agent | xiejianjun000 | 自动化脚本治理 | 工具化思维 目录即服务 | Python | 2026 |
| **OPENHUMAN** | OpenHuman | Tiny Humans AI | 个人AI超级智能 | 本地优先记忆中心 | Rust+TS | 2026.01 |
| **OPENWORKER** | OpenWorker | Andrew Ng | 交付成品的AI同事 | 交付成品而非对话 | Python+TS | 2026.07 |

---

### 1. OpenClaw — MCP 标准奠基者

**核心架构：7 层模型**
```
Loop      → 核心循环（think → tool_calls → observe）
Tools     → 工具系统（bash/read/write/edit/search）
Memory    → 记忆系统（会话 + 持久）
Planning  → 规划系统（Plan-as-Tool 自主分解）
Rules     → 行为约束（CLAUDE.md / .cursorrules）
Skills    → 领域知识（SKILL.md 渐进式加载）
MCP       → 工具插件化（JSON-RPC 2.0）
```

**关键特性分析：**

| 特性 | 技术实现 | 对ECO价值 | 采纳 |
|------|---------|-----------|------|
| MCP协议标准 | JSON-RPC 2.0 | ★★★★★ ECO MCP直接复用 | 强制 |
| 渐进式Skill | 三级加载(meta→instructions→resources) | ★★★★★ 执法技能按需加载 | 强制 |
| Rule即CLAUDE.md | Markdown规则注入系统提示词 | ★★★★★ ECO宪法文件 | 强制 |
| Plan-as-Tool | plan注册为LLM可调用工具 | ★★★★☆ 复杂案件多步规划 | 推荐 |
| Agent Team编排 | Orchestrator + 专业Agent + 模型分层 | ★★★★★ 执法团队编排 | 推荐 |
| Per-Agent MCP | agents字段过滤Server可见性 | ★★★★☆ 角色权限隔离 | 参考 |
| Gateway网关 | 文件级持久记忆+通道管理 | ★★★☆☆ 参考 | 参考 |
| MCP作用域管理 | 多Agent共享MCP vs 独占MCP | ★★★★☆ ECO MCP权限设计 | 参考 |

**Agent Team 模式（参考架构）：**
```
Orchestrator (主模型)
  ├── Indexer Agent      → 法规索引
  ├── Searcher Agent     → 法规检索
  ├── Reviewer Agent     → 法条审查
  ├── Memory Agent       → 执法案例记忆
  ├── Security Agent     → 执法风险扫描
  └── Planner Agent      → 执法计划分解
```


### 2. Hermes Agent — 自进化通用 Agent 框架

**核心架构：5 层模型**
```
Entry Layer              → 20+平台适配器 (CLI/Telegram/Discord/微信/飞书)
Core Loop Layer          → 同步循环 (think → tool_calls → observe)
Tool & Intelligence Layer → 70+自注册工具 / 记忆 / Skills / 审批门
Execution Layer          → 6后端 (Local/Docker/SSH/Modal/Daytona/Singularity)
Persistence Layer        → SQLite + FTS5 会话/记忆/技能文件
```

**关键特性分析：**

| 特性 | 技术实现 | 对ECO价值 | 采纳 |
|------|---------|-----------|------|
| **5层架构** | Entry→Core→Tool→Execution→Persistence | ★★★★★ ECO层次设计参考 | 推荐 |
| **自注册工具** | registry.register() 每工具一个文件 | ★★★★★ 执法工具即插即用 | 强制 |
| **四层记忆** | Prompt记忆 + 会话归档 + 技能 + 外部Provider | ★★★★★ 执法案例记忆体系 | 强制 |
| **自进化闭环** | Execute→Track→Evaluate→Reflect→Crystallize→Store | ★★★★★ 执法技能自进化 | 推荐 |
| **背景审查** | 每10轮fork子Agent自动审查+提取Skill | ★★★★☆ 执法经验自动沉淀 | 推荐 |
| **血统压缩** | 摘要→子会话→parent_session_id血统链 | ★★★★☆ 长会话管理 | 参考 |
| **Kaban编排** | 跨进程编排 + SQLite状态持久化 | ★★★★☆ 多任务协调 | 参考 |
| **MoA (Mixture of Agents)** | 4模型并发 + 聚合器 | ★★★☆☆ 多模型裁判 | 参考 |
| **飞书集成** | Hermes Gateway WS连接，飞书群交互 | ★★★★★ ECO飞书入口 | 强制 |
| **提示词缓存优化** | 3层系统提示词(Stable/Context/Volatile) | ★★★★★ 性能优化 | 推荐 |
| **8个专业Profile** | PM/架构/AI/前端/审查/测试/DevOps/文档 | ★★★★★ ECO Profile模板 | 强制 |

**记忆系统深潜（四层）：**

| 层级 | 存储 | 生命周期 | 容量 | 更新延迟 | 检索方式 |
|------|------|---------|------|---------|---------|
| L1 MEMORY.md | 文件 ~800t | 永久(会话间) | ~2200字符 | 下个会话 | 系统提示词注入 |
| L2 USER.md | 文件 ~500t | 永久(会话间) | ~1375字符 | 下个会话 | 系统提示词注入 |
| L3 会话归档 | SQLite FTS5 | 永久 | 全部 | 实时 | session_search工具 |
| L4 外部Provider | 7种可选 | 可配置 | 可扩展 | 实时 | 统一MemoryProvider接口 |

**外部记忆Provider对比：**

| Provider | 定位 | 评分(LongMemEval) | 适合ECO场景 |
|----------|------|-------------------|-------------|
| Hindsight | 知识图谱+结构化事实 | 94.6% | ★★★★★ 法规知识图谱 |
| Honcho | 辩证用户建模 | — | ★★★☆☆ 执法对象画像 |
| Mem0 | 云LLM提取 | 67.6% | ★★★☆☆ 备用 |
| OpenViking | 文件系统层级 | — | ★★★★☆ 法规文件索引 |
| Holographic | 本地SQLite+FTS5+信任评分 | — | ★★★★★ 本地执法记忆 |
| RetainDB | 混合搜索(向量+BM25+重排序) | — | ★★★☆☆ 付费云服务 |
| ByteRover | 预压缩提取+知识树 | — | ★★★★☆ 法规知识树 |


### 3. CLAUDE (FlowWiki) — 生态环境法规知识库主 Agent

**核心架构：宪法驱动型 Agent**
```
CLAUDE.md          → 主Agent身份+职责+工作流程
SCHEMA.md          → 知识库宪法（14维质量+操作纪律+ACE流程）
CHANGELOG.md       → 版本历史
AGENTS.md          → 8个专业Agent定义+ACE协同流程
```

**关键特性分析：**

| 特性 | 描述 | 对ECO价值 | 采纳 |
|------|------|-----------|------|
| 14维质量评分卡 | D1-D14溯源/结构/连接/内容/质量 | ★★★★★ ECO质量保障 | 强制 |
| ACE反思循环 | Generator→Reflector→Curator三级审查 | ★★★★★ 执法内容审查 | 强制 |
| 原文指针铁律 | 每个结论必须追溯到raw/源文件 | ★★★★★ 执法证据追溯 | 强制 |
| 7层知识架构 | L1-L7从原始数据到场景层 | ★★★★★ 知识组织方法论 | 强制 |
| 15个环境要素 | env/air~env/emergency共15个标签 | ★★★★★ ECO要素体系 | 强制 |
| Skill升级通道 | Prompt使用3次→提升为正式Skill | ★★★★☆ 执法技能孵化 | 推荐 |
| 8 Agent职责分离 | Gen/Ref/Cur/Ing/Res/Lint/Mem/SkillMgr | ★★★★★ 职责边界设计 | 强制 |
| 零全文搬运原则 | wiki/只存摘要+判据 | ★★★★★ 执法知识设计 | 强制 |
| 操作纪律(7条) | raw/只读、ACE必经、证据可追溯 | ★★★★★ ECO操作规范 | 强制 |
| 70_Prompt库 | 12个可复用提示词模板 | ★★★★☆ 执法提示词模板 | 推荐 |

**ACE反思循环流程：**
```
Generator:  依据raw/源文件生成执法知识摘要
    ↓ 交付草案
Reflector:  逐项核验法条准确性、时效性、完整性
    ↓ 校验结论
Curator:    最终决策 — 通过/退回/标记人工
    ↓
写入wiki/       ← 仅通过的内容才能入库
```

### 4. CODEX (FlowWiki) — 自动化脚本治理 Agent

**核心架构：工具化思维**
```
CODEX.md     → 身份+权限+协作边界
_scripts/    → 自动化工具箱（30+ Python脚本）
  ├── quality_audit.py  → 14维质量审计
  ├── lint.py           → 断链/孤页/指针检查
  ├── fix_*.py          → 渐进式批量修复
  ├── reindex.py        → 索引重建
  └── batch_ingest.py   → 批量入库
```

**关键特性分析：**

| 特性 | 描述 | 对ECO价值 | 采纳 |
|------|------|-----------|------|
| 职责边界清晰 | 代码Agent只处理脚本，知识问题委托主Agent | ★★★★★ Agent边界设计 | 强制 |
| _scripts/工具箱 | 目录即服务，每个脚本单一功能 | ★★★★★ 工具组织方式 | 强制 |
| 多阶段审计 | lint→quality_audit→fix渐进式改进 | ★★★★★ 质量持续改进 | 强制 |
| 批量修复流水线 | fix_*.py系列，渐进式修复策略 | ★★★★☆ 数据批量修复 | 推荐 |
| 只读约束 | 禁止修改raw/源文件 | ★★★★★ 证据保全 | 强制 |


### 5. OPENHUMAN — 个人AI超级智能（记忆中心型）

**核心架构：Graph编排 + Memory Tree**
```
Desktop App (Tauri + React)
    ↕ IPC (JSON-RPC 2.0)
openhuman-core (Rust)
  ├── Memory Tree        ← SQLite + Markdown vault (Obsidian兼容)
  ├── Orchestrator       ← tinyagents Graph引擎
  ├── Subconscious Loop  ← 后台思考循环
  ├── Sub-agent Fleets   ← 3层深度delegation + 12 archetype
  ├── TokenJuice压缩     ← 内容感知压缩(JSON/Code/Log/HTML)
  └── Split Brain        ← Reflex(快速) + Reasoning(深度) + Subconscious(后台)
```

**关键特性分析：**

| 特性 | 技术实现 | 对ECO价值 | 采纳 |
|------|---------|-----------|------|
| **Memory Tree** | 评分Markdown块→SQLite，人类可读可编辑 | ★★★★★ ECO记忆体系核心 | 强制 |
| **Graph编排** | tinyagents状态机+DAG，可中断/恢复 | ★★★★★ 执法流程编排 | 强制 |
| **Subconscious** | 后台循环：加载→评估→执行→记录 | ★★★★★ 法规时效监控 | 强制 |
| **Durable Checkpoint** | SQLite持久化状态，断点续跑 | ★★★★★ 多步执法审批 | 强制 |
| **Split Brain** | Reflex+Reasoning+Subconscious三重架构 | ★★★★☆ 执法快速+深度分析 | 推荐 |
| **TokenJuice压缩** | 内容感知，减少80% token消耗 | ★★★★☆ 长法规文档处理 | 推荐 |
| **Sub-agent Fleets** | 3层delegation，12个内置archetype | ★★★★★ 执法团队 | 推荐 |
| **E2E加密A2A** | Signal协议跨实例Agent协作 | ★★★☆☆ 跨省执法协同 | 参考 |
| **自动化数据摄取** | 118+ OAuth轮询每20分钟 | ★★★★☆ 法规自动更新监控 | 推荐 |
| **Obsidian兼容** | Memory Tree = Obsidian笔记 | ★★★★★ 直接融合Obsidian | 强制 |

**Memory Tree 深潜：**

```
Memory Tree 数据流：
  外部服务(118+ OAuth) → 数据摄取
    → 标准化Markdown块(<=3000t) + 评分
    → SQLite存储 + Obsidian兼容Markdown库
    → 用户可直接在Obsidian中打开编辑

分层加载策略：
  热点(当前会话) → 温区(近期活跃) → 冷区(长期归档)

检索方式：混合检索
  BM25全文搜索 + 语义向量 + BGE交叉编码重排序 + RRF融合


### 6. OPENWORKER — 交付成品的AI同事（安全优先型）

**核心架构：3层+Risk Model**
```
Desktop App (Tauri 2 + React)
    ↕
Local Agent Server (Python/FastAPI + aisuite)
  ├── Agent Engine         ← aisuite Agents API
  ├── 25+ Connectors       ← GitHub/Slack/Jira/Notion/Gmail等
  ├── MCP Client           ← mcpServers标准兼容
  ├── Risk Model           ← READ/WRITE_LOCAL/EXEC/EXTERNAL
  └── Unattended Operation ← Inbox + Scheduler + Self-wake
```

**关键特性分析：**

| 特性 | 技术实现 | 对ECO价值 | 采纳 |
|------|---------|-----------|------|
| **Risk Model** | 4级风险(READ/WRITE/EXEC/EXTERNAL) | ★★★★★ 执法工具权限控制 | 强制 |
| **Operating Modes** | 5种模式(discuss/plan/interactive/auto/custom) | ★★★★★ 执法不同场景 | 强制 |
| **Agent Types** | chat/code/cowork/myhelper/ops | ★★★★★ ECO 5种执法Agent | 强制 |
| **MCP标准兼容** | mcpServers格式跨平台 | ★★★★★ 与Hermes/Claude Code兼容 | 强制 |
| **SKILL.md格式** | Anthropic标准格式 | ★★★★★ 与Hermes一致 | 强制 |
| **Unattended Inbox** | 无人时挂起，回来审核 | ★★★★☆ 执法审批 | 推荐 |
| **25+ Connectors** | GitHub/Slack/Jira等 | ★★★★☆ 对接政务系统 | 推荐 |
| **ProviderRouter** | provider:前缀智能路由 | ★★★★★ 国产模型兼容 | 强制 |
| **aisuite** | 统一LLM接口 | ★★★★★ 多模型兼容 | 强制 |
| **审批收件箱** | 风险操作挂起→用户审核 | ★★★★★ 执法审批流程 | 强制 |



---

## 第三部分：ECO AGENT 记忆系统融合设计（OPENHUMAN Memory Tree × 其他5框架）

### 融合设计原则

OPENHUMAN 的 Memory Tree 作为**记忆基础设施**，融合其他框架的记忆模式：

| 框架记忆模式 | 融合到Memory Tree的方式 | 存储格式 | 检索方式 |
|-------------|----------------------|---------|---------|
| **Hermes 4层记忆** | L1(L2) → Memory Tree常驻节点；L3(会话) → Tree时间线；L4(外部) → Tree插件 | Markdown+评分 | FTS5+向量 |
| **CLAUDE FlowWiki** | raw/ → 原文节点；wiki/ → 知识节点；自动同步到Memory Tree | Markdown(Obsidian原生) | BM25+向量+重排序 |
| **CODEX脚本** | 审计结果→Tree质量节点；修复记录→Tree操作日志 | JSON+Markdown | 标签检索 |
| **OpenClaw Skills** | SKILL.md → Tree技能节点；渐进式加载 | Markdown+YAML | 元数据过滤 |
| **OPENWORKER记忆** | 会话→Tree情节记忆；审批→Tree决策节点 | Markdown+风险标签 | Risk过滤 |

### ECO Memory Tree 数据模型

```
eco-memory-tree/
├── statutes/                 ← 法规知识（FlowWiki同步）
│   ├── 生态环境法典/
│   ├── 大气污染防治法/
│   └── ... (按要素分类)
│
├── enforcement_cases/        ← 执法案例（含评分+标签）
│   ├── 处罚案例/
│   ├── 复议案例/
│   └── 诉讼案例/
│
├── penalty_benchmarks/       ← 裁量基准（各省结构化数据）
│   ├── 国家基准/
│   └── 各省基准/
│
├── procedures/               ← 执法程序（状态机定义）
│   ├── 普通程序/
│   ├── 简易程序/
│   └── 听证程序/
│
├── quality/                  ← 质量审计记录（CODEX模式）
│   ├── audit_logs/
│   └── fix_history/
│
├── sessions/                 ← 会话历史（Hermes模式）
│   └── timeline/
│
├── skills/                   ← 执法技能（OpenClaw SKILL.md格式）
│   ├── enforcement-skill/
│   └── research-skill/
│
└── subconscious/             ← 后台监控（OPENHUMAN模式）
    ├── statute_watch/        ← 法规时效监控
    ├── case_alerts/          ← 案件时间节点提醒
    └── update_reports/       ← 更新报告
```

## 第四部分：Obsidian 深度融合方案

### Obsidian 作为 ECO AGENT 的 First-Class Citizen

ECO AGENT 将 Obsidian 作为**知识层的基础设施**，而非可选附件：

```
┌──────────────────────────────────────┐
│          ECO AGENT Runtime           │
│  (Hermes Profile / taiji-agent)     │
└────────────┬─────────────────────────┘
             │ MCP (JSON-RPC 2.0)
┌────────────▼─────────────────────────┐
│       Obsidian MCP 桥接层 ★           │
│                                      │
│  ┌────────────────────────────┐      │
│  │ enquire-mcp / obsidian-mcp │      │
│  │ 46个工具 / 22个工具         │      │
│  │ BM25+向量+重排序+RRF融合    │      │
│  │ 尊重wikilink/frontmatter/标签│      │
│  └──────────┬─────────────────┘      │
└─────────────┼────────────────────────┘
              │ 读取/搜索/写入
┌─────────────▼────────────────────────┐
│           Obsidian Vault ★            │
│                                      │
│  raw/ → 原文（只读，执法证据）        │
│  wiki/ → 知识（编译后，执法参考）     │
│  .memory/ → 操作日志+ZK卡片          │
│  memory-tree/ → ECO Memory Tree      │
│  enforcement/ → 执法案例+文书        │
│  quality/ → 审计报告+评分历史        │
└──────────────────────────────────────┘
```

### 选用的 Obsidian MCP 方案

| 方案 | 选用原因 | 工具数 | 关键能力 |
|------|---------|-------|---------|
| **enquire-mcp** | ★ 最全面的检索能力 | 46 | BM25+ML+BGE重排序+RRF融合，HNSW实时索引，PDF+OCR |
| **obsidian-mcp** | ★ round-trip安全，尊重Obsidian约定 | 22 | wikilink/frontmatter/tag保留，7个Claude Skills |
| **AILSS** | ★ Python生态，Ontology导向 | 自定义 | LangGraph工作流，本体引导检索 |

### Obsidian 在 ECO AGENT 中的具体角色

| 功能 | Obsidian实现 | ECO AGENT 使用方式 |
|------|-------------|-------------------|
| **法规知识库** | FlowWiki wiki/ + raw/ | eco-knowledge MCP通过Obsidian MCP桥读取 |
| **执法案例库** | enforcement/cases/ 目录 | Memory Tree节点↔Markdown文件双向同步 |
| **裁量基准** | enforcement/benchmarks/ | 结构化YAML frontmatter + 表格 |
| **执法文书** | enforcement/documents/ | 模板生成→Obsidian存储→审批 |
| **质量审计** | quality/audit/ + quality/scores/ | CODEX风格脚本写入Obsidian |
| **技能存储** | skills/目录 | OpenClaw SKILL.md格式 |
| **后台监控** | .subconscious/ 目录 | Subconscious循环写入监控报告 |
