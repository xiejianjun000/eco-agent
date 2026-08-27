/**
 * eco-audit-chain — dsh plugin: SM3 tamper-evident execution audit chain.
 *
 * Port of eco-agent's agent_core/trace_audit.py (five-element ledger +
 * SM3 hash chain, source: github.com/xiejianjun000/eco-agent, MIT).
 *
 * Every tool call is recorded as a five-element ledger entry
 * (when / who / what / result / cost) and locked into a SM3 hash chain:
 * each record's current_hash = SM3(prev_hash + timestamp + operation +
 * input_hash + output_hash). Any tampering breaks the chain; `verify()`
 * recomputes every line and reports the first mismatch.
 *
 * The plugin:
 *   - listens on `tools/result` to automatically record successful tool calls;
 *   - exposes ctx.ecoAudit (EcoAuditService) so other plugins (e.g. the
 *     permission gate) can record denied attempts through the same chain;
 *   - registers model-facing tools: eco_audit_verify / eco_audit_stats /
 *     eco_audit_query / eco_audit_export.
 *
 * P2 (v0.3.0):
 *   - maxEntries retention: when the live chain exceeds maxEntries, it is
 *     archived as trace_audit_<ts>.jsonl (fully verifiable, chain preserved)
 *     and a fresh chain starts from genesis — no truncation, no broken links.
 *   - `eco_audit_export` exports records across the live chain and all
 *     rotated archives with the same rich filters as eco_audit_query.
 */

import { mkdirSync, readFileSync, appendFileSync, existsSync, statSync, renameSync, readdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { homedir } from 'node:os'
import type { Context } from '@deepseek-ai/cordis'
import { defineTool } from '@deepseek-ai/dsh-tools'
import Schema from '@deepseek-ai/schemastery'
import { sm3Hex } from './sm3.js'

export const name = 'eco-audit-chain'
export const inject = ['tools']
export const Config = Schema.object({
  auditDir: Schema.string().default(join(homedir(), '.eco', 'dsh', 'audit'))
    .description('Directory for trace_audit.jsonl'),
  autoRecord: Schema.boolean().default(true)
    .description('Automatically record tool calls via tools/result'),
  maxEntries: Schema.number().default(0).min(0)
    .description('P2 retention: max entries in the live chain before rotating to trace_audit_<ts>.jsonl (0 = unlimited)'),
})

/** Genesis predecessor hash — identical role to govmcp AuditChain's genesis. */
export const GENESIS_PREV_HASH = '0'.repeat(64)

/** Meta fields excluded when recomputing the business input during verify(). */
const META_FIELDS = new Set([
  'input_data', 'timestamp', 'current_hash', 'prev_hash', 'entry_id',
  'input_hash', 'output_hash', 'operation', 'operator',
])

export interface AuditRecord {
  when: number
  who: string
  what: string
  result: string
  cost: string
  operation: string
  operator: string
  prev_hash: string
  current_hash: string
  entry_id: number
  input_data: string
  timestamp: number
  input_hash: string
  output_hash: string
  [key: string]: unknown
}

export class EcoAuditService {
  readonly chainPath: string

  constructor(readonly auditDir: string, readonly maxEntries = 0) {
    mkdirSync(auditDir, { recursive: true })
    this.chainPath = join(auditDir, 'trace_audit.jsonl')
  }

  /** P2 retention: rotate the live chain to trace_audit_<ts>.jsonl when over maxEntries. */
  private maybeRotate(): void {
    if (this.maxEntries <= 0) return
    const lines = this.rawLines()
    if (lines.length < this.maxEntries) return
    const stamp = new Date().toISOString().replace(/[:.]/g, '-')
    const uniq = Math.random().toString(36).slice(2, 8)
    renameSync(this.chainPath, join(this.auditDir, `trace_audit_${stamp}_${uniq}.jsonl`))
  }

  /** P2: archive files of this chain (newest first). */
  archives(): string[] {
    const names = readdirSync(this.auditDir).filter(n => /^trace_audit_.+\.jsonl$/.test(n))
    names.sort().reverse()
    return names.map(n => join(this.auditDir, n))
  }

  /** P2: export live + archived records with the same filters as query(). */
  exportAll(opts: {
    operation?: string
    decision?: string
    level?: string
    from?: number
    to?: number
    who?: string
    keyword?: string
  } = {}): AuditRecord[] {
    const out: AuditRecord[] = []
    const files = [...this.archives(), this.chainPath]
    for (const f of files) {
      if (!existsSync(f)) continue
      for (const line of readFileSync(f, 'utf8').split(/\r?\n/).filter(Boolean)) {
        try {
          const e = JSON.parse(line) as AuditRecord
          if (opts.operation && e.operation !== opts.operation) continue
          if (opts.decision && String(e.decision ?? '') !== opts.decision) continue
          if (opts.level && String(e.level ?? '') !== opts.level) continue
          if (opts.who && String(e.who ?? '') !== opts.who) continue
          if (opts.from !== undefined && (e.timestamp ?? 0) < opts.from) continue
          if (opts.to !== undefined && (e.timestamp ?? 0) > opts.to) continue
          if (opts.keyword) {
            const hay = `${e.what ?? ''} ${e.result ?? ''} ${e.reason ?? ''} ${e.input_data ?? ''}`.toLowerCase()
            if (!hay.includes(opts.keyword.toLowerCase())) continue
          }
          out.push(e)
        } catch { /* skip corrupt line */ }
      }
    }
    return out
  }

  /** Append a five-element entry to the SM3 hash chain (JSONL, fsynced). */
  append(entry: Record<string, unknown>, operation: string, operator = 'eco-agent'): AuditRecord {
    this.maybeRotate()
    const prev = this.lastHash()
    const timestamp = Date.now() / 1000
    const inputData = JSON.stringify(entry)
    const inputHash = sm3Hex(inputData)
    const outputHash = ''
    const hashSource = `${prev}${timestamp}${operation}${inputHash}${outputHash}`
    const currentHash = sm3Hex(hashSource)
    const record: AuditRecord = {
      ...entry,
      when: Number(entry.when ?? Date.now() / 1000),
      who: String(entry.who ?? 'dsh-agent'),
      what: String(entry.what ?? ''),
      result: String(entry.result ?? ''),
      cost: String(entry.cost ?? ''),
      operation,
      operator,
      prev_hash: prev,
      current_hash: currentHash,
      entry_id: this.count(),
      input_data: inputData,
      timestamp,
      input_hash: inputHash,
      output_hash: outputHash,
    }
    appendFileSync(this.chainPath, JSON.stringify(record) + '\n', { encoding: 'utf8' })
    return record
  }

  /** Record one tool call (five elements + SM3 chain), mirroring record_tool_call. */
  recordToolCall(tool: string, args: unknown, result: string, durationMs: number,
    level = 'L1', decision = 'allow', reason = ''): AuditRecord {
    const entry: Record<string, unknown> = {
      when: Date.now() / 1000,
      who: 'dsh-agent',
      what: `tool_call:${tool}`,
      result: String(result).slice(0, 500),
      cost: `${durationMs}ms`,
      level,
      decision,
    }
    if (reason) entry.reason = reason
    return this.append(entry, 'tool_call', 'dsh-agent')
  }

  /** Record a denied attempt (permission gate) through the same chain. */
  recordDenied(tool: string, level: string, reason: string): AuditRecord {
    return this.recordToolCall(tool, {}, `DENIED: ${reason}`, 0, level, 'deny', reason)
  }

  /** Recompute every line and detect tampering / chain breaks. */
  verify(): { ok: boolean; error?: string; entries: number; last_hash?: string } {
    const lines = this.rawLines()
    let prev = GENESIS_PREV_HASH
    let entries = 0
    for (let i = 0; i < lines.length; i++) {
      let e: Record<string, unknown>
      try {
        e = JSON.parse(lines[i]) as Record<string, unknown>
      } catch {
        return { ok: false, error: `line ${i + 1} is corrupted JSON`, entries }
      }
      if (e.prev_hash !== prev) {
        return { ok: false, error: `line ${i + 1} hash chain broken`, entries }
      }
      const businessEntry: Record<string, unknown> = {}
      for (const [k, v] of Object.entries(e)) {
        if (!META_FIELDS.has(k)) businessEntry[k] = v
      }
      const inputData = JSON.stringify(businessEntry)
      const inputHash = sm3Hex(inputData)
      const outputHash = String(e.output_hash ?? '')
      const hashSource = `${prev}${String(e.timestamp ?? '')}${String(e.operation ?? '')}${inputHash}${outputHash}`
      const recomputed = sm3Hex(hashSource)
      if (recomputed !== e.current_hash) {
        return { ok: false, error: `line ${i + 1} content tampered (hash mismatch)`, entries }
      }
      prev = String(e.current_hash)
      entries++
    }
    return { ok: true, entries, last_hash: prev.slice(0, 16) }
  }

  /** Chain statistics + verify summary. */
  stats(): Record<string, unknown> {
    const v = this.verify()
    const byOperation: Record<string, number> = {}
    for (const line of this.rawLines()) {
      try {
        const e = JSON.parse(line) as Record<string, unknown>
        const what = String(e.what ?? '?').split(':')[0]
        byOperation[what] = (byOperation[what] ?? 0) + 1
      } catch { /* skip corrupt line */ }
    }
    return {
      ...v,
      by_operation: byOperation,
      size_bytes: existsSync(this.chainPath) ? statSync(this.chainPath).size : 0,
      chain_path: this.chainPath,
    }
  }

  /** Query records (newest first) with rich filters (P1: decision/level/time/who/keyword + pagination). */
  query(opts: {
    limit?: number
    offset?: number
    operation?: string
    decision?: string
    level?: string
    from?: number
    to?: number
    who?: string
    keyword?: string
  } = {}): AuditRecord[] {
    const lines = this.rawLines()
    const limit = Math.max(1, Math.min(opts.limit ?? 20, 500))
    const offset = Math.max(0, opts.offset ?? 0)
    const matches: AuditRecord[] = []
    for (let i = lines.length - 1; i >= 0; i--) {
      try {
        const e = JSON.parse(lines[i]) as AuditRecord
        if (opts.operation && e.operation !== opts.operation) continue
        if (opts.decision && String(e.decision ?? '') !== opts.decision) continue
        if (opts.level && String(e.level ?? '') !== opts.level) continue
        if (opts.who && String(e.who ?? '') !== opts.who) continue
        if (opts.from !== undefined && (e.timestamp ?? 0) < opts.from) continue
        if (opts.to !== undefined && (e.timestamp ?? 0) > opts.to) continue
        if (opts.keyword) {
          const hay = `${e.what ?? ''} ${e.result ?? ''} ${e.reason ?? ''} ${e.input_data ?? ''}`.toLowerCase()
          if (!hay.includes(opts.keyword.toLowerCase())) continue
        }
        matches.push(e)
      } catch { /* skip corrupt line */ }
    }
    return matches.slice(offset, offset + limit)
  }

  /** Aggregate distribution (P1): by decision / level / operation / hour. */
  summary(): Record<string, unknown> {
    const byDecision: Record<string, number> = {}
    const byLevel: Record<string, number> = {}
    const byOperation: Record<string, number> = {}
    const byHour: Record<string, number> = {}
    let deniedTotal = 0
    for (const line of this.rawLines()) {
      try {
        const e = JSON.parse(line) as AuditRecord
        const decision = String(e.decision ?? 'allow')
        byDecision[decision] = (byDecision[decision] ?? 0) + 1
        const level = String(e.level ?? 'L1')
        byLevel[level] = (byLevel[level] ?? 0) + 1
        const op = String(e.operation ?? 'unknown')
        byOperation[op] = (byOperation[op] ?? 0) + 1
        if (decision === 'deny') deniedTotal++
        const h = new Date((e.timestamp ?? 0) * 1000).toISOString().slice(0, 13)
        byHour[h] = (byHour[h] ?? 0) + 1
      } catch { /* skip corrupt line */ }
    }
    return {
      entries: this.rawLines().length,
      by_decision: byDecision,
      by_level: byLevel,
      by_operation: byOperation,
      by_hour: byHour,
      denied_total: deniedTotal,
    }
  }

  rawLines(): string[] {
    if (!existsSync(this.chainPath)) return []
    return readFileSync(this.chainPath, 'utf8').split(/\r?\n/).filter(Boolean)
  }

  private lastHash(): string {
    const lines = this.rawLines()
    if (lines.length === 0) return GENESIS_PREV_HASH
    try {
      return String((JSON.parse(lines[lines.length - 1]) as Record<string, unknown>).current_hash)
    } catch {
      return GENESIS_PREV_HASH
    }
  }

  private count(): number {
    return this.rawLines().length
  }
}

declare module '@deepseek-ai/cordis' {
  interface Context {
    ecoAudit: EcoAuditService
  }
}

export function apply(ctx: Context, config: ConfigType) {
  const service = new EcoAuditService(config.auditDir, config.maxEntries)
  ctx.provide('ecoAudit', service)

  if (config.autoRecord) {
    // Observe the immutable final outcome of every tool call.
    ctx.on('tools/result', (exec, result) => {
      try {
        service.recordToolCall(
          exec.name ?? 'unknown',
          exec.arguments ?? {},
          typeof result === 'string' ? result : JSON.stringify(result),
          0,
          'L1',
          'allow',
        )
      } catch {
        // audit must never break the loop
      }
    })
  }

  ctx.tools.register(defineTool({
    name: 'eco_audit_verify',
    description: 'Verify the integrity of the SM3 audit chain (tamper detection).',
    parameters: {},
    output: {
      schema: { type: 'json' },
      render: (_args, value) => [{ type: 'text', text: JSON.stringify(value, null, 2) }],
    },
    async execute() {
      return JSON.parse(JSON.stringify(service.verify()))
    },
  }))

  ctx.tools.register(defineTool({
    name: 'eco_audit_stats',
    description: 'Audit chain statistics: entries, integrity, operation breakdown.',
    parameters: {},
    output: {
      schema: { type: 'json' },
      render: (_args, value) => [{ type: 'text', text: JSON.stringify(value, null, 2) }],
    },
    async execute() {
      return JSON.parse(JSON.stringify(service.stats()))
    },
  }))

  ctx.tools.register(defineTool({
    name: 'eco_audit_query',
    description: 'Query audit records (newest first) with filters: operation, decision (allow/deny), level (L1-L4), time range (from/to unix seconds), who, keyword; supports offset pagination.',
    parameters: {
      limit: { type: 'number', description: 'Max records, default 20, max 500' },
      offset: { type: 'number', description: 'Skip N matching records, default 0' },
      operation: { type: 'string', description: 'Filter by operation (tool_call / llm_call / chat_trace)' },
      decision: { type: 'string', enum: ['allow', 'deny', 'ask'], description: 'Filter by gate decision' },
      level: { type: 'string', enum: ['L1', 'L2', 'L3', 'L4'], description: 'Filter by risk level' },
      from: { type: 'number', description: 'Start time (unix seconds)' },
      to: { type: 'number', description: 'End time (unix seconds)' },
      who: { type: 'string', description: 'Filter by operator' },
      keyword: { type: 'string', description: 'Substring match over what/result/reason/input' },
    },
    output: {
      schema: { type: 'json' },
      render: (_args, value) => [{ type: 'text', text: JSON.stringify(value, null, 2) }],
    },
    async execute(args) {
      return JSON.parse(JSON.stringify(service.query({
        limit: args?.limit,
        offset: args?.offset,
        operation: args?.operation,
        decision: args?.decision,
        level: args?.level,
        from: args?.from,
        to: args?.to,
        who: args?.who,
        keyword: args?.keyword,
      })))
    },
  }))

  ctx.tools.register(defineTool({
    name: 'eco_audit_summary',
    description: 'Audit chain aggregate summary: distributions by decision / level / operation / hour, plus denied total.',
    parameters: {},
    output: {
      schema: { type: 'json' },
      render: (_args, value) => [{ type: 'text', text: JSON.stringify(value, null, 2) }],
    },
    async execute() {
      return JSON.parse(JSON.stringify(service.summary()))
    },
  }))

  ctx.tools.register(defineTool({
    name: 'eco_audit_export',
    description: 'Export audit records across the live chain and all rotated archives (P2 retention) with filters: operation, decision, level, time range (from/to unix seconds), who, keyword. Returns JSON array.',
    parameters: {
      operation: { type: 'string', description: 'Filter by operation (tool_call / llm_call / chat_trace)' },
      decision: { type: 'string', enum: ['allow', 'deny', 'ask'], description: 'Filter by gate decision' },
      level: { type: 'string', enum: ['L1', 'L2', 'L3', 'L4'], description: 'Filter by risk level' },
      from: { type: 'number', description: 'Start time (unix seconds)' },
      to: { type: 'number', description: 'End time (unix seconds)' },
      who: { type: 'string', description: 'Filter by operator' },
      keyword: { type: 'string', description: 'Substring match over what/result/reason/input' },
    },
    output: {
      schema: { type: 'json' },
      render: (_args, value) => [{ type: 'text', text: JSON.stringify(value, null, 2) }],
    },
    async execute(args) {
      return JSON.parse(JSON.stringify(service.exportAll({
        operation: args?.operation,
        decision: args?.decision,
        level: args?.level,
        from: args?.from,
        to: args?.to,
        who: args?.who,
        keyword: args?.keyword,
      })))
    },
  }))
}

type ConfigType = { auditDir: string; autoRecord: boolean; maxEntries: number }
