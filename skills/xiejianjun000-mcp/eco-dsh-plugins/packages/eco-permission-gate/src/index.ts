/**
 * eco-permission-gate — dsh plugin: L1-L4 risk permission gate.
 *
 * Port of eco-agent's agent_core/permissions.py (source:
 * github.com/xiejianjun000/eco-agent, MIT).
 *
 * Risk levels (aligned with eco-agent PERMISSION.md):
 *   L1 READ         read-only queries           -> auto allow
 *   L2 WRITE_LOCAL  local safe-zone writes      -> auto allow
 *   L3 EXEC         command/code execution      -> whitelist allow, else per mode
 *   L4 EXTERNAL     external service writes     -> ask (default) or deny
 *
 * The gate hooks `tools/pre-execute`, decides allow/ask/deny, and forwards
 * denied attempts to ctx.ecoAudit when the eco-audit-chain plugin is loaded.
 *
 * P1 additions:
 *   - Hot-reloadable policy: `eco_policy_reload` tool + ctx.ecoPolicy service
 *     re-read PERMISSION.md / riskOverrides at runtime (no plugin restart).
 *   - Three-plugin linkage: when recordDeniedToMemory=true and the
 *     eco-memory-tree plugin is loaded, denied attempts are also written into
 *     the memory tree as tagged security events.
 *
 * P2 (v0.3.0) additions — declarative wildcard rule engine:
 *   - `rules` config: ordered allow/ask/deny rules matching tool-name globs
 *     (`mcp__*`, `shell_*`), parameter value globs (e.g. `rm -rf*`), and
 *     workspace path globs. Evaluation is first-match-wins, mirroring the
 *     ecosystem standard (dsh-permission-rules / dsh-permissions / dsh-gov):
 *     write the denials first and the permissive rules last.
 *   - Rules run BEFORE the L1-L4 risk ladder, so a rule can both harden a
 *     read-only tool (deny) and unlock an otherwise-ask L4 tool (allow).
 *
 * Tool risk resolution: rules > PERMISSION.md / config overrides > prefix map > L3 default.
 * mcp__{server}__{tool} remote tools always resolve to L3 (server is untrusted;
 * a write operation can masquerade as a query_* name) unless explicitly
 * overridden — same conservative rule as the original.
 */

import { existsSync, readFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { join } from 'node:path'
import type { Context } from '@deepseek-ai/cordis'
import type { PreToolDecision, ToolExecution } from '@deepseek-ai/dsh-tools'
import { defineTool } from '@deepseek-ai/dsh-tools'
import Schema from '@deepseek-ai/schemastery'

declare module '@deepseek-ai/cordis' {
  interface Context {
    ecoAudit?: { recordDenied(tool: string, level: string, reason: string): void }
    ecoMemory?: {
      add(content: string, score?: number, tags?: string[], parentId?: string | null): { id: string }
    }
    ecoPolicy?: { reload(): { ok: boolean; overrides: Record<string, string>; loaded_from?: string } }
  }
}

export const name = 'eco-permission-gate'
// ecoAudit / ecoMemory 为可选联动依赖：对应插件加载后才写入；未加载时静默跳过
export const inject = ['tools', 'ecoAudit']

export const LEVEL_LABELS = { L1: 'READ', L2: 'WRITE_LOCAL', L3: 'EXEC', L4: 'EXTERNAL' } as const
export type RiskLevel = keyof typeof LEVEL_LABELS

const LEVELS: RiskLevel[] = ['L1', 'L2', 'L3', 'L4']

/** Default prefix -> risk map (order is priority, first match wins). */
const PREFIX_RISK: Array<[string[], RiskLevel]> = [
  // L3 — command/code execution
  [['execute_code', 'execute_', 'shell', 'exec_'], 'L3'],
  // L4 — external service writes (gov procedures / approvals / trading / device control / network writes)
  [['apply_', 'book_', 'submit_', 'register_', 'trade_', 'set_',
    'configure_', 'control_', 'dispatch_', 'handle_', 'initiate_',
    'manage_', 'input_', 'generate_approval_document',
    'apply_approval_digital_signature'], 'L4'],
  // L2 — local safe-zone writes
  [['workspace_', 'memory_', 'generate_', 'write_', 'save_'], 'L2'],
  // L1 — read-only queries / retrieval / analysis (wide fallback)
  [['query_', 'get_', 'search_', 'kb_', 'calculate_', 'predict_',
    'analyze_', 'detect_', 'vision_', 'ocr_', 'monitor_',
    'supervise_', 'track_', 'read_', 'list_'], 'L1'],
]

const DEFAULT_UNKNOWN_LEVEL: RiskLevel = 'L3' // unknown tools default to EXEC (conservative)

/** Default L3 command whitelist (aligned with PERMISSION.md allow_auto). */
const DEFAULT_L3_WHITELIST = [
  'python _scripts/lint.py',
  'python _scripts/quality_audit.py',
  'git ',
  'pip install ',
]

export const Config = Schema.object({
  mode: Schema.union(['auto', 'ask', 'deny']).default('ask')
    .description('L3 non-whitelist handling: auto=allow, ask=user approval, deny=reject'),
  l4Mode: Schema.union(['ask', 'deny']).default('ask')
    .description('L4 external-write handling: ask=user approval (default), deny=reject'),
  nonInteractive: Schema.boolean().default(false)
    .description('When true, treat every call as non-interactive: ask becomes deny'),
  riskOverrides: Schema.dict(String).default({})
    .description('Per-tool risk overrides, e.g. { "web_search": "L1" }'),
  l3Whitelist: Schema.array(String).default([])
    .description('Additional L3 command-prefix whitelist entries'),
  policyFile: Schema.string().default('')
    .description('Optional PERMISSION.md path; its tool_risk_overrides block is loaded'),
  recordDeniedToMemory: Schema.boolean().default(false)
    .description('P1 linkage: write denied attempts into the memory tree (needs eco-memory-tree)'),
  rules: Schema.array(Schema.object({
    match: Schema.object({
      tools: Schema.array(String).default([])
        .description('Tool-name globs, e.g. ["mcp__*", "shell_*", "query_*"]'),
      params: Schema.dict(String).default({})
        .description('Param key -> value glob, e.g. { "command": "rm -rf*" }'),
      paths: Schema.array(String).default([])
        .description('Workspace path globs matched against stringified arguments'),
    }).default({ tools: [], params: {}, paths: [] }),
    action: Schema.union(['allow', 'ask', 'deny']).required()
      .description('Decision when the rule matches'),
    reason: Schema.string().default('')
      .description('Optional reason surfaced in ask/deny and audit'),
  }).description('Ordered first-match-wins rules: denials first, permissive rules last')).default([])
    .description('P2 declarative wildcard rules (tool glob / param glob / path glob)'),
}).description('eco-permission-gate configuration')

interface PolicyRule {
  match: { tools: string[]; params: Record<string, string>; paths: string[] }
  action: 'allow' | 'ask' | 'deny'
  reason: string
}

interface PolicyState {
  overrides: Record<string, string>
  baseOverrides: Record<string, string> // config-provided overrides (re-applied on reload)
  mode: 'auto' | 'ask' | 'deny'
  l4Mode: 'ask' | 'deny'
  nonInteractive: boolean
  whitelist: string[]
  policyFile: string
  recordDeniedToMemory: boolean
  rules: PolicyRule[]
  loadedFrom: string
}

export function apply(ctx: Context, config: ConfigType) {
  const state: PolicyState = {
    overrides: {},
    baseOverrides: { ...config.riskOverrides },
    mode: config.mode,
    l4Mode: config.l4Mode,
    nonInteractive: config.nonInteractive,
    whitelist: [...config.l3Whitelist],
    policyFile: config.policyFile,
    recordDeniedToMemory: config.recordDeniedToMemory,
    rules: normalizeRules(config.rules ?? []),
    loadedFrom: '',
  }
  state.overrides = resolveOverrides(state)

  /** Reload policy at runtime: re-parse PERMISSION.md + re-merge config overrides. */
  function reload(): { ok: boolean; overrides: Record<string, string>; rules: number; loaded_from?: string } {
    state.overrides = resolveOverrides(state)
    state.mode = config.mode
    state.l4Mode = config.l4Mode
    state.nonInteractive = config.nonInteractive
    state.whitelist = [...config.l3Whitelist]
    state.rules = normalizeRules(config.rules ?? [])
    return { ok: true, overrides: { ...state.overrides }, rules: state.rules.length, loaded_from: state.loadedFrom || undefined }
  }

  ctx.provide('ecoPolicy', { reload })

  ctx.on('tools/pre-execute', async (exec: ToolExecution, next): Promise<PreToolDecision> => {
    const toolName = exec.name ?? 'unknown'
    // P2: declarative wildcard rules run first (first match wins).
    const ruleHit = matchRule(toolName, exec, state.rules)
    if (ruleHit) {
      if (ruleHit.action === 'allow') return next()
      if (ruleHit.action === 'ask' && !state.nonInteractive) {
        return { kind: 'ask', reason: `[eco-permission-gate rule] ${toolName} requires approval: ${ruleHit.reason || ruleHit.action}` }
      }
      deny(ctx, toolName, 'RULE', `denied by rule: ${ruleHit.reason || '(no reason)'}`, state)
      return { kind: 'deny', reason: `[eco-permission-gate rule] ${toolName} denied: ${ruleHit.reason || '(no reason)'}` }
    }

    const level = toolRiskLevel(toolName, state.overrides)

    if (level === 'L1' || level === 'L2') {
      return next() // auto allow
    }

    if (level === 'L3') {
      const cmd = extractCommand(exec)
      if (cmd && isWhitelisted(cmd, state)) {
        return next() // whitelist auto allow
      }
      if (state.mode === 'auto') return next()
      if (state.mode === 'ask' && !state.nonInteractive) {
        return { kind: 'ask', reason: `[eco-permission-gate L3/EXEC] ${toolName}${cmd ? `: ${cmd.slice(0, 80)}` : ''}` }
      }
      deny(ctx, toolName, level, `non-whitelisted L3 denied (mode=${state.mode})`, state)
      return { kind: 'deny', reason: `[eco-permission-gate L3/EXEC] ${toolName} denied by policy (mode=${state.mode}). Command: ${cmd.slice(0, 120) || '(none)'}` }
    }

    // L4 — external writes
    if (state.l4Mode === 'ask' && !state.nonInteractive) {
      return { kind: 'ask', reason: `[eco-permission-gate L4/EXTERNAL] ${toolName} calls external service / performs a write. Requires approval.` }
    }
    deny(ctx, toolName, level, `L4 denied (mode=${state.l4Mode})`, state)
    return { kind: 'deny', reason: `[eco-permission-gate L4/EXTERNAL] ${toolName} denied by policy (mode=${state.l4Mode}).` }
  })

  ctx.tools.register(defineTool({
    name: 'eco_policy_reload',
    description: 'Hot-reload the permission policy (PERMISSION.md + config overrides) without restarting the plugin. Returns the effective tool risk overrides.',
    parameters: {},
    output: {
      schema: { type: 'json' },
      render: (_args, value) => [{ type: 'text', text: JSON.stringify(value, null, 2) }],
    },
    async execute() {
      return JSON.parse(JSON.stringify(reload()))
    },
  }))
}

/** Resolve risk level: overrides > prefix map > L3 default. */
export function toolRiskLevel(toolName: string, overrides: Record<string, string>): RiskLevel {
  if (toolName in overrides) {
    const lvl = overrides[toolName].toUpperCase()
    if ((LEVELS as string[]).includes(lvl)) return lvl as RiskLevel
  }
  for (const [prefixes, level] of PREFIX_RISK) {
    if (prefixes.some((p) => toolName.startsWith(p))) return level
  }
  return DEFAULT_UNKNOWN_LEVEL
}

/** Minimal glob matcher: '*' matches any sequence (including empty). No deps. */
export function globMatch(pattern: string, value: string): boolean {
  if (!pattern) return false
  if (pattern === '*') return true
  if (!pattern.includes('*')) return pattern === value
  const parts = pattern.split('*')
  let rest = value
  for (let i = 0; i < parts.length; i++) {
    const part = parts[i]
    if (part === '') continue
    if (i === 0) {
      if (!rest.startsWith(part)) return false
      rest = rest.slice(part.length)
    } else if (i === parts.length - 1) {
      return rest.endsWith(part)
    } else {
      const idx = rest.indexOf(part)
      if (idx === -1) return false
      rest = rest.slice(idx + part.length)
    }
  }
  return true
}

function normalizeRules(rules: PolicyRule[]): PolicyRule[] {
  return rules.map((r) => ({
    match: {
      tools: r.match?.tools ?? [],
      params: r.match?.params ?? {},
      paths: r.match?.paths ?? [],
    },
    action: r.action,
    reason: r.reason ?? '',
  }))
}

/** First-match-wins rule evaluation over tool glob / param glob / path glob. */
function matchRule(toolName: string, exec: ToolExecution, rules: PolicyRule[]): PolicyRule | null {
  if (!rules || rules.length === 0) return null
  const args = (exec.arguments ?? {}) as Record<string, unknown>
  const argsText = JSON.stringify(args ?? {})
  for (const rule of rules) {
    const m = rule.match
    const toolHit = m.tools.length === 0 || m.tools.some((g) => globMatch(g, toolName))
    if (!toolHit) continue
    let paramHit = true
    for (const [key, pattern] of Object.entries(m.params)) {
      const val = args?.[key]
      const s = typeof val === 'string' ? val : JSON.stringify(val ?? '')
      if (!globMatch(pattern, s)) { paramHit = false; break }
    }
    if (!paramHit) continue
    const pathHit = m.paths.length === 0 || m.paths.some((g) => globMatch(g, argsText))
    if (!pathHit) continue
    return rule
  }
  return null
}

function extractCommand(exec: ToolExecution): string {
  const args = (exec.arguments ?? {}) as Record<string, unknown>
  return String(args.command ?? args.code ?? args.script ?? '')
}

function isWhitelisted(cmd: string, state: PolicyState): boolean {
  const wl = [...DEFAULT_L3_WHITELIST, ...state.whitelist]
  return wl.some((w) => {
    const prefix = w.trim()
    return prefix && cmd.startsWith(prefix)
  })
}

/** Load PERMISSION.md tool_risk_overrides block (no YAML dependency), then merge config. */
function resolveOverrides(state: PolicyState): Record<string, string> {
  const merged: Record<string, string> = { ...state.baseOverrides }
  const text = readPermissionMd(state.policyFile)
  if (!text) return merged
  // tool_risk_overrides:\n  - tool: xxx\n    level: Lx
  const re = /-\s*tool:\s*([A-Za-z0-9_]+)\s*\n\s*level:\s*(L[1-4])/g
  let m: RegExpExecArray | null
  while ((m = re.exec(text)) !== null) {
    merged[m[1]] = m[2].toUpperCase()
  }
  state.loadedFrom = state.policyFile || ''
  return merged
}

function readPermissionMd(policyFile: string): string {
  const candidates: string[] = []
  if (policyFile) candidates.push(policyFile)
  const env = process.env.ECO_PROFILES_DIR
  if (env) candidates.push(join(env, 'eco-agent', 'PERMISSION.md'))
  candidates.push(join(homedir(), '.eco', 'profiles', 'eco-agent', 'PERMISSION.md'))
  for (const p of candidates) {
    if (p && existsSync(p)) {
      try { return readFileSync(p, 'utf8') } catch { /* try next */ }
    }
  }
  return ''
}

/** Forward a denied decision to the audit chain and (optionally) the memory tree.
 *  Uses ctx.get() so both targets stay optional (no inject requirement):
 *  a service that is absent or not provided returns undefined instead of throwing. */
function deny(ctx: Context, tool: string, level: string, reason: string, state: PolicyState): void {
  try {
    ctx.get('ecoAudit')?.recordDenied(tool, level, reason)
  } catch {
    // audit must never break the gate
  }
  if (state.recordDeniedToMemory) {
    try {
      ctx.get('ecoMemory')?.add(
        `[SECURITY] denied ${tool} (${level}): ${reason.slice(0, 200)}`,
        3,
        ['security', 'denied', tool],
        null,
      )
    } catch {
      // memory must never break the gate either
    }
  }
}

type ConfigType = {
  mode: 'auto' | 'ask' | 'deny'
  l4Mode: 'ask' | 'deny'
  nonInteractive: boolean
  riskOverrides: Record<string, string>
  l3Whitelist: string[]
  policyFile: string
  recordDeniedToMemory: boolean
  rules?: PolicyRule[]
}
