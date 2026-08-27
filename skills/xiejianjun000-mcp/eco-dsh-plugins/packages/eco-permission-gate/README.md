# eco-permission-gate

dsh plugin — L1-L4 风险权限闸门。

> 移植自 [xiejianjun000/eco-agent](https://github.com/xiejianjun000/eco-agent) 的 `agent_core/permissions.py`（MIT License），能力对齐原版五级风险分级思路（L1-L4 + 默认 L3）。

## 作用

在 dsh 的工具调用前拦截（`tools/pre-execute` 钩子），按工具名/命令前缀解析风险等级，自动放行安全操作、对高危操作要求用户确认或直接拒绝：

| 级别 | 含义 | 默认行为 |
|------|------|----------|
| L1 | READ（只读查询） | 自动放行 |
| L2 | WRITE_LOCAL（本地安全区写入） | 自动放行 |
| L3 | EXEC（命令/代码执行） | 白名单自动放行，其余按 mode（auto/ask/deny） |
| L4 | EXTERNAL（外部服务写入） | 默认 ask，可配 deny |

等级解析顺序：`PERMISSION.md / 配置覆盖` > `前缀映射` > `默认 L3`。`mcp__{server}__{tool}` 远程工具一律保守解析为 L3。

## v0.2.0 — 策略热更新 + 三插件联动

- 新增 `eco_policy_reload` 工具：运行时重新解析 `PERMISSION.md` 与配置 overrides，无需重启插件；同时提供 `ctx.ecoPolicy.reload()` 服务。
- 新增 `recordDeniedToMemory` 配置：开启后每次拒绝事件自动写入记忆树（`[SECURITY]` 前缀 + `security/denied/tool` 标签），配合 eco-memory-tree 形成安全事件记忆。
- 联动采用 `ctx.get()` 读取可选服务，未加载审计链 / 记忆树时静默降级，不影响权限闸门独立使用。

## v0.3.0 — 声明式通配符规则引擎

- 新增 `rules` 配置：有序的 `allow / ask / deny` 规则，支持工具名 glob（`tools: ["mcp__*", "shell_*"]`）、参数 glob（`params: { command: "rm -rf*" }`）、路径 glob（`paths: ["/workspace/tmp/*"]`），**first-match-wins**，先于 L1-L4 分级执行。
- 生态对齐：遵循 dsh 生态（dsh-permission-rules / dsh-permissions / dsh-gov）惯例——拒绝规则写在前面、放行规则写在最后。
- `eco_policy_reload` 返回体新增 `rules` 字段（当前生效规则数），热更新无需重启。

## 安装

```bash
npm install @eco-dsh/eco-permission-gate
```

```ts
import * as ecoPermissionGate from '@eco-dsh/eco-permission-gate'

app.plugin(ecoPermissionGate, {
  mode: 'ask',        // L3 非白名单：auto 放行 / ask 确认 / deny 拒绝
  l4Mode: 'ask',      // L4：ask / deny
  nonInteractive: false,
  riskOverrides: { web_search: 'L1' },
  l3Whitelist: ['python _scripts/lint.py'],
  policyFile: '',     // 可选 PERMISSION.md 路径
})
```

## 与 eco-audit-chain 联动

被拒绝的调用会通过 `ctx.ecoAudit.recordDenied()` 写入审计链（需同时加载 eco-audit-chain），拒绝事件可追溯。

## 配置项

| 字段 | 默认 | 说明 |
|------|------|------|
| `mode` | `ask` | L3 非白名单处理 |
| `l4Mode` | `ask` | L4 处理 |
| `nonInteractive` | `false` | 非交互模式下 ask 降级为 deny |
| `riskOverrides` | `{}` | 工具级覆盖，如 `{ "web_search": "L1" }` |
| `l3Whitelist` | `[]` | 追加 L3 命令前缀白名单 |
| `policyFile` | `''` | PERMISSION.md 路径（`tool_risk_overrides` 块会被解析） |

## 许可

MIT。原始实现版权归 [xiejianjun000/eco-agent](https://github.com/xiejianjun000/eco-agent) 所有，本包为 dsh 生态移植版。
