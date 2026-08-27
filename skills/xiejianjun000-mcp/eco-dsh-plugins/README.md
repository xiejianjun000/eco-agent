# eco-dsh-plugins

dsh 生态插件包 —— 移植自 [xiejianjun000/eco-agent](https://github.com/xiejianjun000/eco-agent) 的三项核心能力，全部为纯 TypeScript、零原生依赖，可直接作为 dsh (DeepSeek Harness) Cordis 插件加载。

| 包 | 移植来源 | 核心能力 |
|----|----------|----------|
| `@eco-dsh/eco-permission-gate` | `permissions.py` | L1-L4 风险分级权限闸门（pre-execute 钩子） |
| `@eco-dsh/eco-audit-chain` | `trace_audit.py` | SM3 防篡改审计链（tools/result 自动记录 + verify） |
| `@eco-dsh/eco-memory-tree` | `memory_tree.py` | 评分制记忆树 + BM25/中文检索 + Obsidian 双向同步 |

## 三件套如何配合

```
eco-permission-gate  tools/pre-execute 决定 allow/ask/deny
        │  deny 时
        ▼
eco-audit-chain     tools/result 自动记录全部工具调用 + recordDenied 记录拒绝事件
        │
        ▼
eco-memory-tree     评分制记忆树沉淀长期上下文，检索时按 score 加成
```

权限闸门把危险操作拦在门前，审计链把所有动作（含被拒的）锁进防篡改账本，记忆树把有效信息沉淀为可检索的长期记忆 —— 三者正好覆盖 dsh 生态最热门的"安全 + 可观测 + 记忆"赛道。

## 安装

```bash
# 三件套全装
npm install @eco-dsh/eco-permission-gate @eco-dsh/eco-audit-chain @eco-dsh/eco-memory-tree
```

```ts
import { Context } from '@deepseek-ai/cordis'
import * as ecoPermissionGate from '@eco-dsh/eco-permission-gate'
import * as ecoAuditChain from '@eco-dsh/eco-audit-chain'
import * as ecoMemoryTree from '@eco-dsh/eco-memory-tree'

export function apply(ctx: Context) {
  ctx.plugin(ecoAuditChain, { auditDir: '~/.eco/dsh/audit' })
  ctx.plugin(ecoPermissionGate, { mode: 'ask', l4Mode: 'ask' })
  ctx.plugin(ecoMemoryTree, { obsidianVault: '/path/to/vault' })
}
```

## 开发

```bash
npm install
npm run build     # 编译三个包到各自 lib/
```

## 来源与许可

三个包均为 [xiejianjun000/eco-agent](https://github.com/xiejianjun000/eco-agent)（MIT）核心模块的 dsh 移植版。原始实现版权归原作者所有；本仓库仅做能力移植与 dsh 适配。
