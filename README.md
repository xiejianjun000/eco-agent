# Eco Agent

> **让 AI 智能体像生命体一样持续进化、像蜂群一样协作、像原生应用一样融入数字世界。**

Eco Agent 是一个开源自主 AI 智能体系统。它内置五层嵌套循环，让 AI 在无人唤醒时也能思考、在无人纠正时也能进化。

[![Version](https://img.shields.io/badge/version-5.0.0--alpha-blue)](CHANGELOG.md)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12%2B-orange)](https://python.org)

## 设计理念

大多数 AI 智能体是"一问一答"的提线木偶——你唤醒它才工作，你关闭它就停止。Eco Agent 希望打破这个模式。

它拥有五层嵌套循环，从毫秒级到天级层层递进：

```
L1 ReAct++  → 置信度门控，不自信时暂停反思
L2 Task     → 多 Agent 协作执行，失败后自动重规划
L3 Pulse    → 每 5-20 分钟一次后台心跳，静默维护
L4 Evolve   → 每次任务后自动学习，每天一次元认知进化
L5 Heal     → 异常自动修复，崩溃后自愈
```

## 核心能力

| 能力 | 说明 |
|:-----|:------|
| **五层循环** | ReAct++ → Task → Pulse → Evolve → Heal，五重生命节律 |
| **自我进化** | 主动学习、技能自动生成、A-B 测试、群体智慧 |
| **多智能体协作** | 动态组队、并行执行、弹性伸缩、资源协商 |
| **统一网关** | 飞书 / 企微 / 钉钉 / Telegram / Discord / Slack / CLI / Web 8 通道 |
| **51 个连接器** | 12 类第三方服务统一接入，凭证 AES-256 加密 |
| **Token 压缩** | 多策略压缩，关键信息保留率 > 95% |
| **韧性自愈** | 熔断器、优雅降级、检查点快照、异常自动修复 |

## 快速开始

```bash
# 克隆仓库
git clone https://github.com/xiejianjun000/eco-agent.git
cd eco-agent

# 安装依赖
pip install -r requirements.txt

# 启动守护进程
python gateway/daemon.py start

# 运行五层循环自检
python agent_core/eco_loops_integration.py --self-test
```

## 项目结构

```
gateway/          统一网关（8 通道接入）
agent_core/       Agent 核心（五层循环 + 多智能体）
_scripts/         自动化工具脚本
skills/           技能库（自动进化生成）
plugins/          插件市场
docs/             文档
```

## 文档

- [GitHub 仓库](https://github.com/xiejianjun000/eco-agent)
- [GitHub Pages](https://xiejianjun000.github.io/eco-agent/)

## 许可证

MIT License © 2026 Eco Agent Team
