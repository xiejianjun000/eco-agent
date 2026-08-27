# eco-audit-chain

dsh plugin — SM3 防篡改执行审计链。

> 移植自 [xiejianjun000/eco-agent](https://github.com/xiejianjun000/eco-agent) 的 `agent_core/trace_audit.py`（MIT License），保留五要素账本 + SM3 哈希链设计。

## 作用

每次工具调用记录五要素（when / who / what / result / cost）并锁进 SM3 哈希链：

```
current_hash = SM3(prev_hash + timestamp + operation + input_hash + output_hash)
```

任何对历史记录的篡改都会导致链断裂，`verify()` 重算每一行并报告首个不匹配位置。内置纯 TS 零依赖 SM3 实现（`sm3.ts`），无需原生模块。

## v0.2.0 — 查询增强

- `eco_audit_query` 支持多维过滤：`decision`(allow/deny/ask)、`level`(L1-L4)、`operation`、`who`、`keyword`(正文子串)、`from/to`(时间范围)、`offset` 分页。
- 新增 `eco_audit_summary`：按决策 / 风险级别 / 操作类型 / 小时维度聚合统计，返回 `denied_total` 等安全态势指标。

## v0.3.0 — 归档轮转与导出

- 新增 `maxEntries` 配置：live 链超过条数后自动归档为 `trace_audit_<ts>.jsonl` 并从 genesis 开启新链——不截断、不断链，历史归档仍可完整 `verify()`。
- 新增 `eco_audit_export` 工具：跨 live 链与全部归档导出记录，支持与 `eco_audit_query` 相同的多维过滤，适合合规留存与安全取证。

## 安装

```bash
npm install @eco-dsh/eco-audit-chain
```

```ts
import * as ecoAuditChain from '@eco-dsh/eco-audit-chain'

app.plugin(ecoAuditChain, {
  auditDir: '~/.eco/dsh/audit', // 账本 trace_audit.jsonl 目录
  autoRecord: true,             // 自动通过 tools/result 记录
})
```

## 注册工具

| 工具 | 说明 |
|------|------|
| `eco_audit_verify` | 重算整条链，检测篡改/断链 |
| `eco_audit_stats` | 链统计：条目数、完整性、操作分布 |
| `eco_audit_query` | 查询最近记录（可过滤 operation） |

## 编程接口

`ctx.ecoAudit`（`EcoAuditService`）暴露 `append` / `recordToolCall` / `recordDenied` / `verify` / `stats` / `query`，供其他插件（如 eco-permission-gate）写入拒绝事件。

## 配置项

| 字段 | 默认 | 说明 |
|------|------|------|
| `auditDir` | `~/.eco/dsh/audit` | 账本目录 |
| `autoRecord` | `true` | 自动记录工具调用 |

## 许可

MIT。原始实现版权归 [xiejianjun000/eco-agent](https://github.com/xiejianjun000/eco-agent) 所有，本包为 dsh 生态移植版。
