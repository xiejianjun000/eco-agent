# Eco Agent

> **五层循环驱动，持续自我进化的 AI 智能体。**

[![Version](https://img.shields.io/badge/version-5.0.0--alpha-blue)](CHANGELOG.md)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12%2B-orange)](https://python.org)
[![Tests](https://img.shields.io/badge/tests-53%20passed-brightgreen)](TEST_LOG.md)
[![CI](https://github.com/xiejianjun000/eco-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/xiejianjun000/eco-agent/actions/workflows/ci.yml)

Eco Agent 是一个开源自主 AI 智能体系统。它内置五层嵌套循环，从毫秒级到天级，让 AI 在无人唤醒时也能思考，在无人纠正时也能进化。

---

## 核心能力

### 五层嵌套循环（The Eco Loops）

大多数 AI 智能体是"一问一答"的模式——你唤醒它才工作。Eco Agent 拥有五层时间尺度不同的循环，层层嵌套：

| 层级 | 节律 | 做什么 |
|:-----|:------|:--------|
| **L1 ReAct++** | 毫秒~秒 | 置信度评分，低于 0.6 自动暂停反思。工具调用失败自动回滚到上一个安全点 |
| **L2 Task** | 秒~分 | 多 Agent 并行执行，自动解析任务依赖图（DAG），检测循环依赖后 5 秒内自动破环。失败后最多 2 轮重规划，超额上报 |
| **L3 Pulse** | 5~20 分钟 | 自适应频率后台心跳（电池模式自动降频）。5 个内置步骤：数据同步→差异检测→规则触发→内存整理→主动建议。全部静默执行，不打扰用户 |
| **L4 Evolve** | 每次任务后 / 每日 | 五阶段进化：经验回放→差距分析→技能生成/优化→记忆固化→版本快照。每次进化输出可读报告 `evolution_report.md`，高风险操作需用户确认 |
| **L5 Heal** | 实时 | 异常自动分类（瞬时/持久/死锁），指数退避重试（1s/2s/4s/8s）。熔断器防止雪崩，优雅降级切备用模型。检查点快照支持"时光倒流"撤销 |

### Agent 协作

- **动态自组织**：收到复杂任务后 10 秒内分解为 5+ 子任务，自动组建专业 Agent 团队（分析师/规划师/编码/审查/部署），无需人工指定角色
- **工作树隔离**：多个 Agent 并行修改同一仓库的不同文件时，自动分配独立工作树，避免合并冲突
- **弹性伸缩**：任务积压超过 10 个时自动创建新 Agent 实例（最多 20 并行），空闲自动回收
- **资源协商**：两个 Agent 争用同一资源时，30 秒内自动达成避让协议，不会死锁
- **自动流程发现**：从 20 次同类执行记录中自动提炼高频协作序列，生成可复用的工作流模板（`.ecoflow`）

### 技能系统

- **自动生成**：检测到同一任务模式出现 3 次以上，60 秒内自动生成可复用的 Skill 文件，含参数模板、前置条件、调用示例
- **主动学习**：基于用户行为模式（如每天 17:00 整理日志），提前生成 Skill 草案并推送用户确认
- **A/B 测试**：同一场景新旧 Skill 并行运行，基于成功率自动选择优胜版本，淘汰劣版本。默认保留最近 3 个快照版本，支持回滚
- **群体智慧**：Skill 脱敏后可匿名共享到社区市场，下载高评分（≥4.5 星）Skill 自动适配本地环境
- **跨会话记忆**：四层认知结构（工作记忆/情景记忆/语义记忆/程序记忆），带自动衰减（按艾宾浩斯曲线）与矛盾检测

### 记忆系统（Memory Tree）

- 基于 SQLite + FTS5 全文搜索，支持 BM25 和语义向量混合检索 + RRF 融合排序
- 评分制节点（0-100），自动按访问频率和时效性调整热度
- Obsidian Markdown 双向同步，SQLite ↔ 可编辑文件，系统不覆盖用户手动修改

### 统一网关

跨平台会话共享上下文，统一消息协议。接入状态如实标注：

| 状态 | 通道 |
|:-----|:-----|
| ✅ 已实现 ChannelAdapter（`gateway/channels/`） | Telegram / Discord / Slack |
| ✅ 独立平台 Bot（`gateway/platforms/`，未走适配器接口） | 飞书 / 企业微信 / 钉钉 |
| 🚧 骨架/待接入 | 微信个人号（Wechaty 依赖外部服务）/ CLI / Web API |

- 统一消息协议，已接入通道归一化为 UnifiedMessage
- 会话管理带持久化和过期回收（72 小时自动清理）
- 审计日志记录每条消息的 who/what/when/result/cost 五要素

### 连接器系统

51 个第三方服务连接器，覆盖 12 类：

| 类别 | 数量 | 示例 |
|:-----|:----:|:-----|
| 消息 | 6 | 飞书、企微、钉钉、Telegram、Discord、Slack |
| 代码 | 4 | GitHub、GitLab、Gitee、Bitbucket |
| 文档 | 5 | Notion、Confluence、Google Docs、语雀、飞书文档 |
| 项目 | 4 | Jira、Linear、Trello、Asana |
| 数据 | 5 | Google Drive、Dropbox、OneDrive、S3、Airtable |
| AI | 3 | OpenAI、Anthropic、HuggingFace |
| 邮件 | 3 | Gmail、Outlook、IMAP/SMTP |
| 日历 | 3 | Google Calendar、Outlook Calendar、飞书日历 |
| 设计 | 4 | Figma、Canva、LottieFiles、Iconify |
| 金融 | 4 | Stripe、GitHub Sponsors、Open Collective、Ko-fi |
| 存储 | 4 | 本地文件、Obsidian、SQLite、Redis |

凭证全部采用 Fernet（AES-128-CBC + HMAC-SHA256，cryptography 库）加密存储，磁盘无明文；主密钥由环境变量 `ECO_MASTER_KEY` 提供，未设置时启动随机生成并明确告警。

### 开发治理（G 方法论）

```
G1 宪法治理    Markdown 规则即代码
G2 工具化      每个脚本单一职责
G3 渐进交付    lint → audit → fix 循环
G4 质量门禁    14 维评分 + ACE 三阶段审查
G5 语义版本    CHANGELOG + Git tag
G6 职责分离    知识层与逻辑层解耦
G7 技能孵化    3 次使用 → 升级为 Skill
G8 可追溯性    原文指针 + 操作日志
```

---

## 快速开始

```bash
# 克隆
git clone https://github.com/xiejianjun000/eco-agent.git
cd eco-agent

# 安装依赖
pip install -r requirements.txt

# 配置环境变量（Kimi LLM + 加密主密钥）
cp .env.example .env
# 编辑 .env 填入 KIMI_API_KEY（https://platform.moonshot.cn 申请）与 ECO_MASTER_KEY

# 运行单元测试（离线规则降级模式，不耗 API 配额）
pytest tests/

# 真实 LLM 冒烟测试（需要有效 KIMI_API_KEY）
python scripts/smoke_kimi.py

# 启动守护进程
python gateway/daemon.py start

# 五层循环自检
python agent_core/eco_loops_integration.py --self-test
```

---

## 测试状态

| 模块 | 文件 | 测试数 |
|:-----|:-----|:------:|
| L1 ReAct++ | tests/modules/test_react_loop.py | 3 |
| L2 Commander | tests/modules/test_commander.py | 5 |
| L5 Self-Healing | tests/modules/test_self_healing.py | 4 |
| Memory + Token | tests/modules/test_memory.py | 5 |
| Evolution + Skills | tests/modules/test_evolution.py | 6 |

并行执行：`python tests/run_all.py` · 历史记录：[TEST_LOG.md](TEST_LOG.md)

---

## 项目结构

```
gateway/           统一网关（6 通道已接入，CLI/Web/微信骨架待接入）
agent_core/        五层循环 + 多智能体 + 记忆 + 技能 + 进化 + 自愈
_scripts/          自动化工具脚本（质量审计、lint、修复流水线）
skills/            技能库（自动进化生成）
plugins/           插件市场
benchmarks/        基准测试框架（HumanEval / MBPP / OSWorld）
docs/              架构文档
```

---

## 开源协议

MIT License © 2026 Eco Agent Team
