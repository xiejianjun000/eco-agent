# Eco Agent

> **让 AI 智能体像生命体一样持续进化、像蜂群一样协作、像原生应用一样融入数字世界。**

Eco Agent 是一个面向未来的开源自主 AI 智能体系统，对标并全面超越 Claude、Codex、Hermes、OpenClaw、OpenHuman 等当前最前沿产品。

[![Version](https://img.shields.io/badge/version-5.0.0--alpha-blue)](CHANGELOG.md)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12%2B-orange)](https://python.org)

## 核心能力

| 能力 | 说明 | 对标 |
|:-----|:------|:------|
| **五层循环** | ReAct++ → Task → Pulse → Evolve → Heal | 超越 Claude/Codex/Hermes/OpenHuman |
| **自我进化** | 主动学习/技能自动生成/A-B测试/群体智慧 | 超越 Hermes |
| **多智能体协作** | 动态自组织/并行执行/弹性伸缩/协商 | 超越 Codex + OpenHuman |
| **8 平台网关** | 飞书/企微/钉钉/Telegram/Discord/Slack/CLI/Web | 超越 OpenClaw |
| **51 连接器** | 12 类服务统一接入 | 超越 OpenHuman |
| **Token 压缩** | 压缩比 < 1%，RAG 准确率 > 95% | 超越所有竞品 |
| **韧性自愈** | 熔断/降级/检查点快照/时光倒流 | **独创** |

## 快速开始

```bash
# 安装
git clone https://github.com/eco-agent/eco-agent.git
cd eco-agent
pip install -r requirements.txt

# 启动
python gateway/daemon.py start

# 五层循环自检
python agent_core/eco_loops_integration.py --self-test
```

## 架构

```
gateway/          统一网关（8 通道接入）
agent_core/       Agent 核心（五层循环 + 多智能体）
_scripts/         工具脚本（33+ 自动化工具）
skills/           技能库（自动进化生成）
plugins/          插件市场（社区贡献）
```

## 五层循环

| 层级 | 节律 | 文件 | 超越对象 |
|:-----|:------|:------|:---------|
| L1 ReAct++ | ms~s | `react_loop.py` | Claude (置信度门控+中断) |
| L2 Task | s~min | `commander_v2.py` | Codex (动态重规划) |
| L3 Pulse | 5~20min | `heartbeat.py` | OpenHuman (自适应频率) |
| L4 Evolve | 每日 | `meta_evolution.py` | Hermes (五阶段+版本迭代) |
| L5 Heal | 实时 | `self_healing.py` | **独创** (竞品未系统实现) |

## 许可证

MIT License © 2026 Eco Agent Team
