# Eco Agent

> **五层循环驱动，持续自我进化的 AI 智能体。**

## 核心能力

### 五层嵌套循环

| 层级 | 节律 | 做什么 |
|:-----|:------|:--------|
| L1 ReAct++ | ms~s | 置信度门控 + 暂停反思 + 原子操作回滚 |
| L2 Task | s~分 | 多Agent并行 + DAG依赖解析 + 自动重规划 |
| L3 Pulse | 5~20min | 自适应后台心跳，静默维护不打扰用户 |
| L4 Evolve | 每日 | 经验回放→差距分析→技能生成→版本迭代 |
| L5 Heal | 实时 | 熔断器 + 降级 + 检查点快照 + 时光倒流 |

### Agent 协作

动态自组织、工作树隔离、弹性伸缩（最多20并行）、跨Agent协商、自动流程发现

### 技能系统

自动生成、主动学习、A/B 测试、群体智慧共享、四层跨会话记忆

### 51 个连接器

覆盖 12 类第三方服务（消息/代码/文档/项目/数据/AI/邮件/日历/设计/金融/存储/政务），Fernet（AES-128-CBC + HMAC）加密存储凭证

### 统一网关

已接入：Telegram / Discord / Slack（ChannelAdapter）+ 飞书 / 企微 / 钉钉（独立 Bot）。
骨架/待接入：CLI、Web API、微信个人号（Wechaty 依赖外部服务）。

## 快速开始

```bash
git clone https://github.com/xiejianjun000/eco-agent.git
cd eco-agent
pip install -r requirements.txt
python gateway/daemon.py start
```

## 开源协议

MIT License
