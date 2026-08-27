/**
 * eco-dsh-plugins — dsh 运行时集成验证
 * 真实 cordis 运行时加载三个插件，走完整 tools 管线（pre-execute / execute / result），
 * 验证：权限闸门决策、审计链自动记录与防篡改、记忆树工具链、Obsidian 双向同步。
 * 在 GitHub Actions CI 中执行：npm run build 之后运行本脚本。
 */
import { mkdtempSync, rmSync, readFileSync, writeFileSync, existsSync, readdirSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createRequire } from 'node:module'

const ROOT = dirname(fileURLToPath(import.meta.url)) // <repo>/scripts
const REPO = join(ROOT, '..')
const PKG = join(REPO, 'packages')

const require = createRequire(join(REPO, 'package.json'))
const { Context } = require('@deepseek-ai/cordis')
const ToolRegistry = require('@deepseek-ai/dsh-tools').default
const { defineTool } = require('@deepseek-ai/dsh-tools')
const SystemPrompt = require('@deepseek-ai/dsh-system-prompt').default
const loadPlugin = async (pkg) => {
  const mod = await import(join(PKG, pkg, 'lib', 'index.js'))
  return { name: mod.name, apply: mod.apply, inject: mod.inject, Config: mod.Config }
}
const gatePlugin = await loadPlugin('eco-permission-gate')
const auditPlugin = await loadPlugin('eco-audit-chain')
const memoryPlugin = await loadPlugin('eco-memory-tree')

let failed = 0
const results = []
function check(name, cond, detail = '') {
  results.push({ name, ok: !!cond, detail })
  if (!cond) failed++
}

// --- 隔离环境 ---
const base = mkdtempSync(join(tmpdir(), 'eco-runtime-'))
const auditDir = join(base, 'audit')
const storeFile = join(base, 'memory', 'tree.json')
const vault = join(base, 'vault')

const ctx = new Context()
await ctx.plugin(SystemPrompt, { persona: 'test' })
await ctx.plugin(ToolRegistry, { mode: 'native' })
await ctx.plugin(gatePlugin, {
  mode: 'deny',            // L3 非白名单直接拒绝
  l4Mode: 'ask',           // L4 需要审批
  nonInteractive: true,    // ask 无审批通道 -> 拒绝
  recordDeniedToMemory: true, // P1 联动：deny 写入记忆树
  // P2 (v0.3.0) declarative wildcard rules — first match wins.
  rules: [
    { match: { tools: ['mcp__*'] }, action: 'deny', reason: 'v3-rules: deny all mcp tools' },
    { match: { tools: ['shell_exec'], params: { command: 'rm*' } }, action: 'deny', reason: 'v3-rules: forbid rm commands' },
    { match: { tools: ['shell_exec'], params: { command: 'ls*' } }, action: 'allow', reason: 'v3-rules: allow ls commands' },
  ],
  riskOverrides: {
    my_query_tool: 'L1',
    // eco 插件自带工具按风险分级放行（系统信任内部工具，读取 L1 / 写入 L2）
    eco_audit_verify: 'L1',
    eco_audit_stats: 'L1',
    eco_audit_query: 'L1',
    eco_audit_summary: 'L1',
    eco_audit_export: 'L1',
    eco_policy_reload: 'L1',
    eco_memory_search: 'L1',
    eco_memory_vector_search: 'L1',
    eco_memory_add: 'L2',
    eco_memory_update: 'L2',
    eco_memory_delete: 'L2',
    eco_memory_prune: 'L2',
    eco_memory_stats: 'L1',
    eco_memory_sync: 'L2',
  },
})
await ctx.plugin(auditPlugin, { auditDir })
await ctx.plugin(memoryPlugin, { storeFile, obsidianVault: vault })

// --- 注册测试工具 ---
const toolDefs = {
  query_users: defineTool({
    name: 'query_users', description: 'read users', parameters: {},
    output: { schema: { type: 'json' }, render: (_a, v) => [{ type: 'text', text: JSON.stringify(v) }] },
    async execute() { return { users: 42 } },
  }),
  workspace_write: defineTool({
    name: 'workspace_write', description: 'write local', parameters: { content: { type: 'string' } },
    output: { schema: { type: 'json' }, render: (_a, v) => [{ type: 'text', text: JSON.stringify(v) }] },
    async execute(a) { return { written: a?.content ?? '' } },
  }),
  shell_exec: defineTool({
    name: 'shell_exec', description: 'run command', parameters: { command: { type: 'string' } },
    output: { schema: { type: 'json' }, render: (_a, v) => [{ type: 'text', text: JSON.stringify(v) }] },
    async execute(a) { return { ran: a?.command ?? '' } },
  }),
  apply_payment: defineTool({
    name: 'apply_payment', description: 'external write', parameters: { amount: { type: 'number' } },
    output: { schema: { type: 'json' }, render: (_a, v) => [{ type: 'text', text: JSON.stringify(v) }] },
    async execute() { return { paid: true } },
  }),
  mcp__filesystem_read: defineTool({
    name: 'mcp__filesystem_read', description: 'mcp filesystem read', parameters: { path: { type: 'string' } },
    output: { schema: { type: 'json' }, render: (_a, v) => [{ type: 'text', text: JSON.stringify(v) }] },
    async execute(a) { return { read: a?.path ?? '' } },
  }),
}
for (const def of Object.values(toolDefs)) ctx.tools.register(def)

const call = (name, args = {}) => ctx.tools.execute({
  callId: `call_${Math.random().toString(36).slice(2, 10)}`,
  name,
  arguments: args,
  signal: new AbortController().signal,
})

// --- 1. 插件装配：工具注册 ---
const ecoTools = ['eco_audit_verify', 'eco_audit_stats', 'eco_audit_query', 'eco_audit_summary', 'eco_audit_export',
  'eco_memory_add', 'eco_memory_search', 'eco_memory_vector_search', 'eco_memory_update',
  'eco_memory_delete', 'eco_memory_stats', 'eco_memory_sync', 'eco_memory_prune', 'eco_policy_reload']
const registered = new Set(ctx.tools.schemas().map((s) => s.name))
check('插件装配: 9 个 eco 工具全部注册', ecoTools.every((t) => registered.has(t)),
  `missing=${ecoTools.filter((t) => !registered.has(t)).join(',') || 'none'}`)
check('服务注入: ctx.ecoAudit 与 ctx.ecoMemory 可用', !!ctx.ecoAudit && !!ctx.ecoMemory)

// --- 2. 权限闸门 ---
const rL1 = await call('query_users')
check('权限闸门: L1 只读自动放行', rL1.isError === false && rL1.value?.users === 42)

const rL2 = await call('workspace_write', { content: 'safe' })
check('权限闸门: L2 本地写自动放行', rL2.isError === false && rL2.value?.written === 'safe')

const rL3Deny = await call('shell_exec', { command: 'rm -rf /tmp/x' })
check('权限闸门: L3 非白名单拒绝', rL3Deny.isError === true && /denied/.test(rL3Deny.error?.message ?? rL3Deny.error?.reason ?? ''))

const rL4 = await call('apply_payment', { amount: 100 })
check('权限闸门: L4 外部写拒绝(无审批通道)', rL4.isError === true)

// --- 2.5 P2: 通配符规则引擎（first-match-wins） ---
const rMcpDeny = await call('mcp__filesystem_read', { path: '/etc/passwd' })
check('P2 规则: 工具 glob mcp__* deny 拦截', rMcpDeny.isError === true &&
  /v3-rules|denied by rule/.test(rMcpDeny.error?.message ?? rMcpDeny.error?.reason ?? ''),
  `reason=${rMcpDeny.error?.reason ?? rMcpDeny.error?.message}`)

const rLsAllow = await call('shell_exec', { command: 'ls -la /tmp' })
check('P2 规则: 参数 glob ls* allow 放行(绕过 L3)', rLsAllow.isError === false && rLsAllow.value?.ran === 'ls -la /tmp')

const rRmDeny = await call('shell_exec', { command: 'rm -rf /tmp/x' })
check('P2 规则: 参数 glob rm* deny 拦截(先于 L3)', rRmDeny.isError === true &&
  /v3-rules|denied by rule/.test(rRmDeny.error?.message ?? rRmDeny.error?.reason ?? ''),
  `reason=${rRmDeny.error?.reason ?? rRmDeny.error?.message}`)

// --- 3. 审计链：自动记录 + 防篡改 ---
const rVerify1 = await call('eco_audit_verify')
check('审计链: 调用后自动记录(含放行/拒绝)', rVerify1.isError === false && rVerify1.value?.ok === true && rVerify1.value?.entries >= 4,
  `entries=${rVerify1.value?.entries}`)

const rStats = await call('eco_audit_stats')
const ops = rStats.value?.by_operation ?? {}
check('审计链: 按操作类型统计(含 tool_call deny)', ops.tool_call >= 4, `by_operation=${JSON.stringify(ops)}`)

const rQuery = await call('eco_audit_query', { limit: 20 })
const denied = (rQuery.value ?? []).filter((e) => e.decision === 'deny')
check('审计链: 拒绝事件同步入链', denied.length >= 2, `denied=${denied.length}`)

// 篡改检测
const auditFile = join(auditDir, 'trace_audit.jsonl')
const lines = readFileSync(auditFile, 'utf8').split('\n').filter(Boolean)
lines[0] = lines[0].replace(/"current_hash":"[0-9a-f]+"/, `"current_hash":"${'a'.repeat(64)}"`)
writeFileSync(auditFile, lines.join('\n') + '\n')
const rVerify2 = await call('eco_audit_verify')
check('审计链: 篡改检测生效', rVerify2.isError === false && rVerify2.value?.ok === false && /tamper|broken/.test(rVerify2.value?.error ?? ''),
  `error=${rVerify2.value?.error}`)

// --- 4. 记忆树：增删改查/搜索/同步 ---
const rAdd = await call('eco_memory_add', { content: '项目采用 SM3 哈希链做审计，参考 eco-agent 实现', score: 3, tags: ['sm3', 'audit'] })
const node1 = rAdd.value?.node
check('记忆树: 新增节点', rAdd.isError === false && !!node1?.id && rAdd.value?.ok === true)

const rAdd2 = await call('eco_memory_add', { content: '老板喜欢喝美式咖啡，加班时提神', score: 5, tags: ['coffee'], parent_id: node1?.id })
const node2 = rAdd2.value?.node
check('记忆树: 子节点挂载', rAdd2.isError === false && node2?.parent_id === node1?.id)

const rSearchEn = await call('eco_memory_search', { query: 'sm3 hash chain', limit: 5 })
check('记忆树: BM25 英文检索命中', rSearchEn.isError === false && (rSearchEn.value ?? []).length >= 1 &&
  (rSearchEn.value ?? [])[0]?.node?.id === node1?.id)

const rSearchZh = await call('eco_memory_search', { query: '咖啡', limit: 5 })
check('记忆树: 中文子串降级检索', rSearchZh.isError === false && (rSearchZh.value ?? []).length >= 1)

const rUpdate = await call('eco_memory_update', { id: node2?.id, score: 9 })
check('记忆树: 更新节点分数', rUpdate.isError === false && rUpdate.value?.node?.score === 9)

const rSync = await call('eco_memory_sync', { direction: 'both' })
check('记忆树: Obsidian 双向同步(导出)', rSync.isError === false && rSync.value?.ok === true && rSync.value?.exported?.length >= 1,
  `exported=${rSync.value?.exported?.length}`)

const rStatsMem = await call('eco_memory_stats')
check('记忆树: 统计(节点数>=2, 标签聚合)', rStatsMem.isError === false && rStatsMem.value?.nodes >= 2 &&
  (rStatsMem.value?.top_tags ?? []).some((t) => t[0] === 'sm3'))

// 观测 vault 文件实际落盘
check('记忆树: vault 目录生成 md 文件', existsSync(vault) && readdirCount(vault) >= 1, `files=${readdirCount(vault)}`)

const rDelete = await call('eco_memory_delete', { id: node1?.id })
check('记忆树: 删除节点', rDelete.isError === false && rDelete.value?.ok === true)

// --- 4.5 P2: 记忆树遗忘机制 eco_memory_prune ---
const rAddLow = await call('eco_memory_add', { content: '临时低价值记忆 待遗忘', score: 0, tags: ['trash'] })
const nodeLow = rAddLow.value?.node
const rAddSec = await call('eco_memory_add', { content: '安全保护测试记忆', score: 0, tags: ['security'] })
const nodeSec = rAddSec.value?.node

const rPruneDry = await call('eco_memory_prune', { min_score: 5, dry_run: true })
check('P2 遗忘: dryRun 预览识别低分候选且不删除', rPruneDry.isError === false && rPruneDry.value?.dry_run === true &&
  (rPruneDry.value?.candidates ?? 0) >= 1 && (rPruneDry.value?.removed ?? 0) === 0,
  `candidates=${rPruneDry.value?.candidates}`)

const rSearchLowBefore = await call('eco_memory_search', { query: '临时低价值', limit: 5 })
check('P2 遗忘: dryRun 后低分节点仍存在', rSearchLowBefore.isError === false && (rSearchLowBefore.value ?? []).some((h) => h?.node?.id === nodeLow?.id))

const rPruneRun = await call('eco_memory_prune', { min_score: 5 })
check('P2 遗忘: 实际执行删除低分节点并保护 security 标签',
  rPruneRun.isError === false && rPruneRun.value?.ok === true && (rPruneRun.value?.removed ?? 0) >= 1 &&
  (rPruneRun.value?.protected ?? 0) >= 1,
  `removed=${rPruneRun.value?.removed}, protected=${rPruneRun.value?.protected}`)

const rSearchLowAfter = await call('eco_memory_search', { query: '临时低价值', limit: 5 })
check('P2 遗忘: 低分节点已删除', rSearchLowAfter.isError === false && !(rSearchLowAfter.value ?? []).some((h) => h?.node?.id === nodeLow?.id))

const rSearchSecAfter = await call('eco_memory_search', { query: '安全保护测试', limit: 5 })
check('P2 遗忘: security 标签节点受保护保留', rSearchSecAfter.isError === false && (rSearchSecAfter.value ?? []).some((h) => h?.node?.id === nodeSec?.id))

// --- 5. P1: 审计链查询增强（过滤 + 分页 + 汇总） ---
const rQDeny = await call('eco_audit_query', { decision: 'deny', limit: 10 })
check('P1 审计: 按 decision=deny 过滤', rQDeny.isError === false && (rQDeny.value ?? []).length >= 2 &&
  (rQDeny.value ?? []).every((e) => e.decision === 'deny'), `denied=${(rQDeny.value ?? []).length}`)

const rQLevel = await call('eco_audit_query', { level: 'L4', limit: 10 })
check('P1 审计: 按 level=L4 过滤', rQLevel.isError === false && (rQLevel.value ?? []).length >= 1 &&
  (rQLevel.value ?? []).every((e) => e.level === 'L4'))

const rQKw = await call('eco_audit_query', { keyword: 'denied', limit: 10 })
check('P1 审计: 按 keyword=denied 过滤', rQKw.isError === false && (rQKw.value ?? []).length >= 2)

const rQOffset = await call('eco_audit_query', { limit: 1, offset: 1 })
check('P1 审计: offset 分页生效', rQOffset.isError === false && (rQOffset.value ?? []).length === 1)

const rSum = await call('eco_audit_summary')
check('P1 审计: summary 分布统计(denied_total>=2, by_decision.deny>=2)',
  rSum.isError === false && (rSum.value?.denied_total ?? 0) >= 2 && ((rSum.value?.by_decision ?? {}).deny ?? 0) >= 2,
  `denied_total=${rSum.value?.denied_total}`)

// --- 6. P1: 权限策略热更新 ---
const rReload = await call('eco_policy_reload')
check('P1 策略: eco_policy_reload 生效并返回 overrides',
  rReload.isError === false && rReload.value?.ok === true && !!rReload.value?.overrides &&
  rReload.value.overrides.eco_audit_summary === 'L1')

// --- 7. P1: 三插件联动 — deny 事件写入记忆树 ---
const rSecSearch = await call('eco_memory_search', { query: 'SECURITY denied', limit: 5 })
check('P1 联动: deny 事件已写入记忆树(security 标签可检索)',
  rSecSearch.isError === false && (rSecSearch.value ?? []).length >= 1 &&
  (rSecSearch.value ?? [])[0]?.node?.tags?.includes('security'),
  `hits=${(rSecSearch.value ?? []).length}`)

// --- 8. P1: 记忆树向量通道降级 ---
const rVec = await call('eco_memory_vector_search', { query: 'sm3 hash chain', limit: 5 })
check('P1 向量: 无 embedding 配置时优雅降级(vector_enabled=false)',
  rVec.isError === false && rVec.value?.vector_enabled === false && Array.isArray(rVec.value?.results))

// --- 9. P2: 审计链导出 eco_audit_export（无归档时返回全量 live） ---
const rExport = await call('eco_audit_export', { decision: 'deny', limit: 100 })
check('P2 审计: eco_audit_export 跨链导出(deny 过滤)', rExport.isError === false && Array.isArray(rExport.value) &&
  (rExport.value ?? []).length >= 2 && (rExport.value ?? []).every((e) => e.decision === 'deny'),
  `exported=${(rExport.value ?? []).length}`)

// --- 10. P2: 审计链 maxEntries 归档轮转（独立 context，不污染主链） ---
const rotDir = join(base, 'audit-rot')
const ctxRot = new Context()
await ctxRot.plugin(SystemPrompt, { persona: 'test' })
await ctxRot.plugin(ToolRegistry, { mode: 'native' })
await ctxRot.plugin(auditPlugin, { auditDir: rotDir, maxEntries: 3 })
for (let i = 0; i < 8; i++) {
  ctxRot.ecoAudit.append({ when: Date.now() / 1000, who: 'rot-test', what: `entry-${i}`, result: 'ok', cost: '0ms' }, 'tool_call', 'rot-test')
}
const archivesRot = ctxRot.ecoAudit.archives()
check('P2 轮转: 超过 maxEntries=3 后生成归档文件', archivesRot.length >= 1, `archives=${archivesRot.length}`)
const rotVerify = ctxRot.ecoAudit.verify()
check('P2 轮转: 归档后 live 链完整可验证(从 genesis 重新开始)',
  rotVerify.ok === true && rotVerify.entries >= 1 && rotVerify.entries < 3,
  `live_entries=${rotVerify.entries}`)
const rotExport = ctxRot.ecoAudit.exportAll()
check('P2 轮转: exportAll 合并 live+归档记录(8 条不丢)',
  rotExport.length === 8, `exported=${rotExport.length}`)
await ctxRot.stop?.()

await ctx.stop?.()

function readdirCount(p) {
  try { return readdirSync(p).length } catch { return 0 }
}
rmSync(base, { recursive: true, force: true })

console.table(results)
console.log(failed === 0 ? `\nALL ${results.length} CHECKS PASSED` : `\n${failed}/${results.length} CHECK(S) FAILED`)
process.exit(failed === 0 ? 0 : 1)
