# Eco Agent

> 让 AI 智能体像生命体一样持续进化、像蜂群一样协作、像原生应用一样融入数字世界。

Eco Agent 是一个面向未来的开源自主 AI 智能体系统，借鉴社区优秀项目的设计理念，探索智能体的自我进化、多智能体协作和设备-云协同等前沿方向。

## 快速导航

- [GitHub 仓库](https://github.com/xiejianjun000/eco-agent)
- [README](/)
- [MIT License](/LICENSE)

## 核心能力

| 能力 | 说明 |
|:-----|:------|
| **五层循环** | ReAct++ → Task → Pulse → Evolve → Heal 五重嵌套生命节律 |
| **自我进化** | 主动学习 / 技能自动生成 / A-B 测试 / 群体智慧 |
| **多智能体协作** | 动态自组织 / 并行执行 / 弹性伸缩 / 跨 Agent 协商 |
| **8 平台网关** | 飞书 / 企微 / 钉钉 / Telegram / Discord / Slack / CLI / Web |
| **51 连接器** | 12 类第三方服务统一接入，AES-256 加密存储 |
| **Token 压缩** | 多策略压缩，RAG 关键信息保留率 > 95% |
| **韧性自愈** | 熔断器 / 优雅降级 / 检查点快照 / 时光倒流 |

## 架构

```
gateway/          统一网关（8 通道接入）
agent_core/       Agent 核心（五层循环 + 多智能体）
_scripts/         工具脚本
skills/           技能库（自动进化生成）
plugins/          插件市场（社区贡献）
```

## 五层循环

| 层级 | 节律 | 说明 |
|:-----|:------|:------|
| L1 ReAct++ | ms~s | 置信度门控 + 暂停反思 + 原子操作回滚 |
| L2 Task | s~min | 动态重规划 + DAG 依赖图 + 长任务快照 |
| L3 Pulse | 5~20min | 自适应频率 + 静默执行 + 智能推送 |
| L4 Evolve | 每日 | 经验回放 + 差距分析 + 技能生成 + 版本迭代 |
| L5 Heal | 实时 | 指数退避 + 熔断器 + 降级策略 + 韧性日志 |

## 快速开始

```bash
git clone https://github.com/xiejianjun000/eco-agent.git
cd eco-agent
pip install -r requirements.txt
python gateway/daemon.py start
```

## 许可证

MIT License © 2026 Eco Agent Team
