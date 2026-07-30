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

## 阶段A：自生成提示词安全 · 纠错采集 · EcoBench-mini

### 1. 双层系统提示词安全机制（`agent_core/prompt_engine.py`）
- **安全层硬编码**：AI 只辅助执法不替代签字、不得建议规避监管、不得提供破坏生态建议等核心准则，任何机制不得修改。
- **动态层追加式注入**：所有动态提示词经规则校验（禁止覆盖/删除安全层语义、禁止解除限制 pattern、禁止词），违规注入拒绝并记日志。
- **L1 反思结构化**：ReAct++ 的 PAUSE & REFLECT 输出 `{问题诊断, 修正指令}`，修正指令经校验后注入后续轮次提示尾部。
- **SM3 链式审计**：每次动态提示词变更（来源/内容/时间/任务ID/是否接受）追加到 `~/.eco/prompt_audit.jsonl`（prev_hash + SM3），`PromptAuditChain().verify_chain()` 全链校验，`eco doctor` 与 `eco evolution --report` 自动展示链验证状态。
- **三阶段执法状态机**：巡查 / 文书 / 评查三套动态层预设，`switch_phase()` 切换。

### 2. 纠错采集（`agent_core/corrections.py`）
- `eco chat` 中 `/correct <内容>` 或自然语言"不对，应该是……"自动识别纠错。
- 持久化到 `~/.eco/corrections.jsonl`（内容/时间/上下文摘要/命中次数）。
- 后续提问时相关纠错作为**高优先级动态注入**（经 prompt_engine 校验层）注入系统提示词。
- 管理：`eco corrections list | remove <id> | clear`。

### 3. EcoBench-mini（`benchmarks/ecobench/`）
- 50 题金标准数据集（`dataset.jsonl`），覆盖法条引用 / 违法认定 / 处罚裁量 / 执法程序 / 法典新旧衔接五大类，每题含 golden_answer、required_citations、key_points。
- `python benchmarks/ecobench/run_ecobench.py [--limit N] [--mock]`：逐题调 LLM，如实计算法条引用准确率与要点 F1，**无封顶/保底**；`ECO_LLM_DISABLE=1` 时走 mock 模式（CI/离线）。
- 最近一次真实跑分（kimi-k2.5，--limit 10）：**法条引用准确率 0.40，要点 F1 0.615**（受 LLM 波动与超时影响，分数如实报告，见 `ecobench_report.json`）。

### 4. EcoBench RAG A/B 对照实验（EHS 知识库检索增强）

**方法**：同一模型 kimi-k2.5、同一评分器、同一批题（题序前 10 题，`--limit 10`）。
- **baseline**：无检索，裸模型直接作答（`run_ecobench.py --limit 10`）。
- **rag**：`--rag` 模式，每题作答前经 MCP（SSE `http://111.230.89.107:8000/sse`，工具 kb_search/kb_read）检索 EHS 知识库，将 top 片段（总长截断至 3000 字符）作为"参考资料"注入答题提示词，要求优先依据参考资料并注明出处；每题检索文件清单记入报告。

**真实分数（本次，如实报告，无封顶/保底）**：

| 组别 | 法条引用准确率 | 要点 F1 |
|:-----|:--------------:|:-------:|
| baseline（本次复跑） | 0.40 | 0.71 |
| rag（EHS 知识库检索增强） | 0.20 | 0.52 |
| rag（复跑第 2 次，稳定性校验） | 0.30 | 0.59 |

逐题（cite / f1）：

| 题号 | EB01 | EB02 | EB03 | EB04 | EB05 | EB06 | EB07 | EB08 | EB09 | EB10 |
|:-----|:-----|:-----|:-----|:-----|:-----|:-----|:-----|:-----|:-----|:-----|
| baseline | 1/.80 | 1/.60 | 0/1.0 | 0/1.0 | 0/.20 | 1/.50 | 0/1.0 | 0/1.0 | 0/.00 | 1/1.0 |
| rag | 0/1.0 | 1/.80 | 0/.00* | 0/1.0 | 0/.60 | 0/.00* | 0/.80 | 0/.00 | 0/.00 | 1/1.0 |

\* EB03 rag 组 LLM 返回空按兜底答案计 0；EB06 rag 组 LLM ReadTimeout 记 [error] 计 0（均如实保留）。

**结论（如实）**：本轮对照中 RAG **未带来提升，反而显著下降**（引用准确率 0.40→0.20，复跑 0.30，均低于基线）。主因：
1. 该 EHS 知识库内容为 flowwiki 技能/合规笔记，检索命中多为 Skill/执行报告模板类文件，**缺少干净的法条原文库**，注入的噪声上下文稀释了模型自身准确的法条记忆；
2. 注入文本中的阿拉伯数字条款写法（"第99条"）诱导模型改用阿拉伯数字作答，与金标准"第九十九条"字面匹配失配（如 EB01 rag 答案内容正确但因写法失配引用计 0）；
3. 长上下文 prompt 增加 LLM 超时风险（EB06）。
启示：RAG 收益强依赖知识库内容质量（法条原文 + 条号规范写法），仅在知识库补齐法条原文后才值得复测。

## 测试状态

| 模块 | 文件 | 测试数 |
|:-----|:-----|:------:|
| L1 ReAct++ | tests/modules/test_react_loop.py | 3 |
| L2 Commander | tests/modules/test_commander.py | 5 |
| L5 Self-Healing | tests/modules/test_self_healing.py | 4 |
| Memory + Token | tests/modules/test_memory.py | 5 |
| Evolution + Skills | tests/modules/test_evolution.py | 6 |
| Prompt Engine（双层提示词/注入校验/审计链） | tests/modules/test_prompt_engine.py | 21 |
| Corrections（纠错采集/注入/管理） | tests/modules/test_corrections.py | 13 |
| EcoBench-mini（评分诚实性/mock 流程） | tests/modules/test_ecobench.py | 6 |
| EcoBench RAG（检索注入流程 mock） | tests/modules/test_ecobench_rag.py | 8 |

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
