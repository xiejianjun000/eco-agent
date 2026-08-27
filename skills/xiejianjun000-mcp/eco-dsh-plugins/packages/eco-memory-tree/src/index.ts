/**
 * eco-memory-tree — dsh plugin: scored memory tree with BM25 search,
 * optional vector search (OpenAI-compatible embeddings) and Obsidian
 * bidirectional sync.
 *
 * Port of eco-agent's agent_core/memory_tree.py (scored nodes, SQLite+FTS5
 * BM25 ranking, Chinese substring fallback, Obsidian vault sync; source:
 * github.com/xiejianjun000/eco-agent, MIT).
 *
 * Design:
 *   - Nodes are scored, taggable, parent-linkable memory entries persisted as
 *     a JSON ledger (zero native deps, runs anywhere dsh runs).
 *   - search() ranks by BM25 over tokenized content; when the query contains
 *     CJK characters the matcher falls back to substring scoring — mirroring
 *     the original SQLite FTS5 + LIKE Chinese degradation.
 *   - Vector channel (P1): when an OpenAI-compatible embedding endpoint is
 *     configured (or an embedding fn is injected via ctx.ecoMemory.setEmbeddingFn),
 *     nodes carry an `embedding` vector and search() blends BM25 + cosine
 *     similarity (weighted). Without embeddings it degrades gracefully to the
 *     pure BM25 path — fully backward compatible.
 *   - Obsidian bidirectional sync: export nodes to Markdown files in a vault
 *     folder (with frontmatter + tags), and import/refresh from Markdown files
 *     the user edits in the vault. Conflicts are resolved by updated_at.
 *
 * Tools: eco_memory_add / eco_memory_search / eco_memory_vector_search /
 *        eco_memory_update / eco_memory_delete / eco_memory_stats /
 *        eco_memory_sync / eco_memory_prune
 *
 * P2 (v0.3.0) — forgetting & maintenance:
 *   - Nodes track last_access (touched on every add/update/search hit).
 *   - `eco_memory_prune` implements aging: drop low-score nodes and nodes
 *     untouched for maxAgeDays. Security-tagged nodes (tags include
 *     'security' or 'denied') are ALWAYS protected so the permission-gate
 *     linkage never loses evidence. Children of removed nodes are promoted
 *     to roots. dryRun=true previews the outcome without deleting.
 */

import { existsSync, mkdirSync, readFileSync, writeFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { homedir } from 'node:os'
import type { Context } from '@deepseek-ai/cordis'
import { defineTool } from '@deepseek-ai/dsh-tools'
import Schema from '@deepseek-ai/schemastery'

export const name = 'eco-memory-tree'
export const inject = ['tools']
export const Config = Schema.object({
  storeFile: Schema.string().default(join(homedir(), '.eco', 'dsh', 'memory', 'memory_tree.json'))
    .description('JSON ledger path for memory nodes'),
  obsidianVault: Schema.string().default('')
    .description('Optional Obsidian vault folder for bidirectional sync (empty = disabled)'),
  syncOnStart: Schema.boolean().default(false)
    .description('Import vault markdown once at plugin start'),
  embeddingEndpoint: Schema.string().default('')
    .description('Optional OpenAI-compatible embeddings endpoint (e.g. https://api.openai.com/v1/embeddings); empty = vector channel disabled'),
  embeddingApiKey: Schema.string().default('')
    .description('API key for the embeddings endpoint (Bearer auth)'),
  embeddingModel: Schema.string().default('text-embedding-3-small')
    .description('Embeddings model name'),
  vectorWeight: Schema.number().default(0.5).min(0).max(1)
    .description('Blend weight for vector similarity when search() fuses BM25 + cosine (1 = vector only, 0 = BM25 only)'),
})

export interface MemoryNode {
  id: string
  content: string
  score: number
  tags: string[]
  parent_id: string | null
  created_at: number
  updated_at: number
  source: string // 'manual' | 'obsidian' | 'import'
  last_access?: number // P2: last read/write touch, used by prune aging
  embedding?: number[] // optional vector channel (P1)
}

/** Security-related tags are protected from pruning (permission-gate linkage). */
const PROTECTED_TAGS = new Set(['security', 'denied'])

const CJK_RE = /[\u4e00-\u9fff]/

/** Minimal BM25-style scorer with Chinese substring fallback. */
function scoreQuery(content: string, query: string): number {
  const q = query.trim().toLowerCase()
  if (!q) return 0
  const c = content.toLowerCase()
  if (CJK_RE.test(q)) {
    // Chinese degradation path: substring hits + character coverage bonus.
    if (!c.includes(q)) {
      // partial coverage: longest common contiguous substring
      let best = 0
      for (let i = 0; i < q.length; i++) {
        for (let len = 1; i + len <= q.length; len++) {
          if (c.includes(q.slice(i, i + len))) best = Math.max(best, len)
        }
      }
      return best >= 2 ? 0.5 + best * 0.1 : 0
    }
    // full substring hit; longer queries get a small boost
    return 5 + q.length * 0.2
  }
  // BM25-ish over whitespace tokens
  const docTokens = c.split(/[^\p{L}\p{N}]+/u).filter(Boolean)
  const queryTokens = q.split(/[^\p{L}\p{N}]+/u).filter(Boolean)
  if (docTokens.length === 0 || queryTokens.length === 0) return 0
  const docLen = docTokens.length
  const avgDocLen = Math.max(docLen, 10)
  const k1 = 1.2
  const b = 0.75
  const tfMap = new Map<string, number>()
  for (const t of docTokens) tfMap.set(t, (tfMap.get(t) ?? 0) + 1)
  let score = 0
  for (const qt of new Set(queryTokens)) {
    const tf = tfMap.get(qt) ?? 0
    if (tf === 0) continue
    const idf = Math.log(1 + (docLen - tf + 0.5) / (tf + 0.5)) // collection of one
    score += idf * ((tf * (k1 + 1)) / (tf + k1 * (1 - b + b * (docLen / avgDocLen))))
  }
  return score
}

/** Cosine similarity between two vectors (0 when malformed). */
export function cosineSim(a: number[], b: number[]): number {
  if (!Array.isArray(a) || !Array.isArray(b) || a.length === 0 || a.length !== b.length) return 0
  let dot = 0
  let na = 0
  let nb = 0
  for (let i = 0; i < a.length; i++) {
    dot += a[i] * b[i]
    na += a[i] * a[i]
    nb += b[i] * b[i]
  }
  if (na === 0 || nb === 0) return 0
  return dot / (Math.sqrt(na) * Math.sqrt(nb))
}

export type EmbeddingFn = (texts: string[]) => Promise<number[][] | null>

export class MemoryTreeService {
  nodes: MemoryNode[] = []
  private dirty = false
  private embeddingFn: EmbeddingFn | null = null
  private embeddingFailed = false

  constructor(
    readonly storeFile: string,
    readonly obsidianVault: string,
    readonly embeddingEndpoint = '',
    readonly embeddingApiKey = '',
    readonly embeddingModel = 'text-embedding-3-small',
    readonly vectorWeight = 0.5,
  ) {
    mkdirSync(join(storeFile, '..'), { recursive: true })
    this.load()
  }

  /** Vector channel availability (endpoint configured OR fn injected). */
  get vectorEnabled(): boolean {
    return !!this.embeddingFn || (!!this.embeddingEndpoint && !this.embeddingFailed)
  }

  /** Inject an external embedding function (other plugins / tests / adapters). */
  setEmbeddingFn(fn: EmbeddingFn | null): void {
    this.embeddingFn = fn
    this.embeddingFailed = false
  }

  /** Fetch embeddings via the configured OpenAI-compatible endpoint. */
  async embedTexts(texts: string[]): Promise<number[][] | null> {
    if (this.embeddingFn) {
      try {
        return await this.embeddingFn(texts)
      } catch {
        return null
      }
    }
    if (!this.embeddingEndpoint) return null
    try {
      const res = await fetch(this.embeddingEndpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(this.embeddingApiKey ? { Authorization: `Bearer ${this.embeddingApiKey}` } : {}),
        },
        body: JSON.stringify({ model: this.embeddingModel, input: texts }),
      })
      if (!res.ok) throw new Error(`embedding http ${res.status}`)
      const data = (await res.json()) as { data?: Array<{ embedding: number[] }> }
      const vecs = (data.data ?? []).map((d) => d.embedding)
      if (vecs.length !== texts.length) throw new Error('embedding count mismatch')
      return vecs
    } catch {
      this.embeddingFailed = true
      return null
    }
  }

  /** Compute (and cache) embeddings for nodes that lack them. Returns count embedded. */
  async ensureEmbeddings(): Promise<number> {
    const missing = this.nodes.filter((n) => !n.embedding)
    if (missing.length === 0) return 0
    const vecs = await this.embedTexts(missing.map((n) => n.content))
    if (!vecs) return 0
    for (let i = 0; i < missing.length; i++) missing[i].embedding = vecs[i]
    this.save()
    return vecs.length
  }

  load(): void {
    if (!existsSync(this.storeFile)) return
    try {
      const raw = JSON.parse(readFileSync(this.storeFile, 'utf8')) as { nodes?: MemoryNode[] }
      this.nodes = Array.isArray(raw.nodes) ? raw.nodes : []
    } catch {
      this.nodes = []
    }
  }

  save(): void {
    mkdirSync(join(this.storeFile, '..'), { recursive: true })
    writeFileSync(this.storeFile, JSON.stringify({ nodes: this.nodes, saved_at: Date.now() }, null, 2), 'utf8')
    this.dirty = false
  }

  add(content: string, score = 1, tags: string[] = [], parentId: string | null = null): MemoryNode {
    const now = Date.now()
    const node: MemoryNode = {
      id: `n_${now.toString(36)}_${Math.random().toString(36).slice(2, 8)}`,
      content,
      score,
      tags,
      parent_id: parentId,
      created_at: now,
      updated_at: now,
      source: 'manual',
      last_access: now,
    }
    this.nodes.push(node)
    this.save()
    // Fire-and-forget: enrich with a vector if the channel is available.
    if (this.vectorEnabled) this.ensureEmbeddings().catch(() => { /* never block writes */ })
    return node
  }

  update(id: string | undefined, patch: { content?: string; score?: number; tags?: string[]; parent_id?: string | null }): MemoryNode | null {
    if (!id) return null
    const node = this.nodes.find((n) => n.id === id)
    if (!node) return null
    if (patch.content !== undefined) {
      node.content = patch.content
      node.embedding = undefined // invalidate stale vector
    }
    if (patch.score !== undefined) node.score = patch.score
    if (patch.tags !== undefined) node.tags = patch.tags
    if (patch.parent_id !== undefined) node.parent_id = patch.parent_id
    node.updated_at = Date.now()
    node.last_access = Date.now()
    this.save()
    if (this.vectorEnabled) this.ensureEmbeddings().catch(() => { /* ignore */ })
    return node
  }

  remove(id: string | undefined): boolean {
    if (!id) return false
    const before = this.nodes.length
    this.nodes = this.nodes.filter((n) => n.id !== id)
    if (this.nodes.length !== before) {
      this.save()
      return true
    }
    return false
  }

  /** Vector-only search: cosine similarity against the query embedding. */
  async searchVector(query: string, limit = 10): Promise<Array<{ node: MemoryNode; relevance: number; vector: number }>> {
    if (!this.vectorEnabled) return []
    await this.ensureEmbeddings()
    const vecs = await this.embedTexts([query])
    if (!vecs || vecs.length === 0) return []
    const qv = vecs[0]
    const hits = this.nodes
      .filter((n) => n.embedding && n.embedding.length === qv.length)
      .map((node) => {
        const sim = cosineSim(node.embedding!, qv)
        return { node, relevance: sim + node.score * 0.05, vector: sim }
      })
      .filter((x) => x.vector > 0)
      .sort((a, b) => b.relevance - a.relevance)
      .slice(0, limit)
    this.touch(hits.map((x) => x.node.id))
    return hits
  }

  /** Hybrid search: BM25 + optional vector blend (weighted). */
  async search(query: string, limit = 10): Promise<Array<{ node: MemoryNode; relevance: number; vector?: number }>> {
    const bm25 = this.nodes
      .map((node) => ({ node, relevance: scoreQuery(node.content, query) + node.score * 0.1 }))
      .filter((x) => x.relevance > 0)

    const w = this.vectorWeight
    if (!this.vectorEnabled || w <= 0 || bm25.length === 0) {
      const out = bm25.sort((a, b) => b.relevance - a.relevance).slice(0, limit)
      this.touch(out.map((x) => x.node.id))
      return out
    }

    // Fuse: normalize both scores to [0,1] then blend; vector is queried on demand.
    let vec: Array<{ node: MemoryNode; relevance: number; vector: number }> = []
    try {
      vec = await this.searchVector(query, this.nodes.length)
    } catch {
      vec = []
    }
    if (vec.length === 0) {
      const out = bm25.sort((a, b) => b.relevance - a.relevance).slice(0, limit)
      this.touch(out.map((x) => x.node.id))
      return out
    }

    const maxB = Math.max(...bm25.map((x) => x.relevance), 1e-9)
    const maxV = Math.max(...vec.map((x) => x.vector), 1e-9)
    const byId = new Map<string, { b: number; v: number }>()
    for (const x of bm25) byId.set(x.node.id, { b: x.relevance / maxB, v: 0 })
    for (const x of vec) {
      const cur = byId.get(x.node.id) ?? { b: 0, v: 0 }
      cur.v = x.vector / maxV
      byId.set(x.node.id, cur)
    }
    const fused = [...byId.entries()]
      .map(([id, s]) => {
        const node = this.nodes.find((n) => n.id === id)!
        return { node, relevance: (1 - w) * s.b + w * s.v, vector: s.v * maxV }
      })
      .sort((a, b) => b.relevance - a.relevance)
      .slice(0, limit)
    this.touch(fused.map((x) => x.node.id))
    return fused
  }

  /** Mark nodes as accessed (P2 aging input); persists lazily via save(). */
  private touch(ids: string[]): void {
    if (ids.length === 0) return
    const now = Date.now()
    let changed = false
    for (const id of ids) {
      const node = this.nodes.find((n) => n.id === id)
      if (node && node.last_access !== now) {
        node.last_access = now
        changed = true
      }
    }
    if (changed) this.save()
  }

  /**
   * P2 forgetting & maintenance: drop low-score and long-unused nodes.
   * Security-tagged nodes are always protected. Children of removed nodes
   * are promoted to roots. dryRun previews without deleting.
   */
  prune(opts: { minScore?: number; maxAgeDays?: number; dryRun?: boolean } = {}): Record<string, unknown> {
    const now = Date.now()
    const minScore = opts.minScore ?? 0
    const maxAgeMs = opts.maxAgeDays && opts.maxAgeDays > 0 ? opts.maxAgeDays * 24 * 3600 * 1000 : 0
    const dryRun = !!opts.dryRun
    const protectedIds = new Set<string>()
    const candidates: MemoryNode[] = []

    for (const node of this.nodes) {
      if (node.tags.some((t) => PROTECTED_TAGS.has(t))) {
        protectedIds.add(node.id)
        continue
      }
      const lastTouch = node.last_access ?? node.updated_at ?? node.created_at
      const scoreLow = node.score < minScore
      const ageOld = maxAgeMs > 0 && (now - lastTouch) > maxAgeMs
      if (scoreLow || ageOld) candidates.push(node)
    }

    const removed: MemoryNode[] = []
    const promoted: string[] = []
    if (!dryRun) {
      const removeIds = new Set(candidates.map((n) => n.id))
      this.nodes = this.nodes.filter((n) => !removeIds.has(n.id))
      // promote children of removed nodes to roots
      for (const node of this.nodes) {
        if (node.parent_id && removeIds.has(node.parent_id)) {
          node.parent_id = null
          promoted.push(node.id)
        }
      }
      removed.push(...candidates)
      this.save()
    }

    return {
      ok: true,
      dry_run: dryRun,
      candidates: candidates.length,
      removed: removed.length,
      promoted: promoted.length,
      protected: protectedIds.size,
      min_score: minScore,
      max_age_days: opts.maxAgeDays ?? 0,
      remaining_nodes: dryRun ? this.nodes.length - candidates.length : this.nodes.length,
      sample: candidates.slice(0, 5).map((n) => ({ id: n.id, score: n.score, content: n.content.slice(0, 60) })),
    }
  }

  stats(): Record<string, unknown> {
    const bySource: Record<string, number> = {}
    const byTag: Record<string, number> = {}
    let withVector = 0
    for (const n of this.nodes) {
      bySource[n.source] = (bySource[n.source] ?? 0) + 1
      for (const t of n.tags) byTag[t] = (byTag[t] ?? 0) + 1
      if (n.embedding) withVector++
    }
    const avgScore = this.nodes.length
      ? this.nodes.reduce((s, n) => s + n.score, 0) / this.nodes.length
      : 0
    return {
      nodes: this.nodes.length,
      avg_score: Number(avgScore.toFixed(2)),
      by_source: bySource,
      top_tags: Object.entries(byTag).sort((a, b) => b[1] - a[1]).slice(0, 10),
      vector_enabled: this.vectorEnabled,
      nodes_with_embedding: withVector,
      store_file: this.storeFile,
      obsidian_vault: this.obsidianVault || null,
    }
  }

  /** Obsidian sync. direction: 'to' | 'from' | 'both'. */
  sync(direction: 'to' | 'from' | 'both'): Record<string, unknown> {
    if (!this.obsidianVault) return { ok: false, error: 'obsidianVault not configured' }
    const exported: string[] = []
    const imported: string[] = []
    if (direction === 'to' || direction === 'both') {
      mkdirSync(this.obsidianVault, { recursive: true })
      for (const n of this.nodes) {
        if (n.source === 'obsidian' && n.tags.length === 0) continue // keep vault clean of unexported imports
        const file = join(this.obsidianVault, `${safeName(n.id)}.md`)
        const frontmatter = [
          '---',
          `id: "${n.id}"`,
          `score: ${n.score}`,
          `tags: [${n.tags.map((t) => `"${t}"`).join(', ')}]`,
          `parent_id: "${n.parent_id ?? ''}"`,
          `updated_at: ${n.updated_at}`,
          '---',
          '',
          n.content,
          '',
        ].join('\n')
        writeFileSync(file, frontmatter, 'utf8')
        exported.push(file)
      }
    }
    if (direction === 'from' || direction === 'both') {
      if (existsSync(this.obsidianVault)) {
        for (const file of readdirSync(this.obsidianVault).filter((f) => f.endsWith('.md'))) {
          const text = readFileSync(join(this.obsidianVault, file), 'utf8')
          const node = parseMarkdownNode(text, file)
          if (!node) continue
          const existing = this.nodes.find((n) => n.id === node.id)
          if (existing && node.updated_at <= existing.updated_at) continue // keep newest
          if (existing) {
            this.update(existing.id, {
              content: node.content,
              score: node.score,
              tags: node.tags,
              parent_id: node.parent_id,
            })
            existing.source = 'obsidian'
          } else {
            this.nodes.push(node)
          }
          imported.push(join(this.obsidianVault, file))
        }
        this.save()
      }
    }
    return { ok: true, direction, exported, imported, nodes: this.nodes.length }
  }

  /** Root nodes + child count, for tree view. */
  tree(): Array<{ node: MemoryNode; children: number }> {
    return this.nodes
      .filter((n) => !n.parent_id)
      .map((n) => ({ node: n, children: this.nodes.filter((c) => c.parent_id === n.id).length }))
  }
}

function safeName(id: string): string {
  return id.replace(/[^A-Za-z0-9_\-]/g, '_')
}

/** Parse an Obsidian markdown note into a MemoryNode (frontmatter + body). */
function parseMarkdownNode(text: string, file: string): MemoryNode | null {
  const m = /^---\n([\s\S]*?)\n---\n([\s\S]*)$/.exec(text)
  const now = Date.now()
  if (!m) return null
  const fm = m[1]
  const body = m[2].trim()
  const read = (key: string): string | null => {
    const r = new RegExp(`^${key}:\\s*(.*)$`, 'm').exec(fm)
    return r ? r[1].trim().replace(/^"|"$/g, '') : null
  }
  const id = read('id') ?? `obs_${file.replace(/\.md$/, '')}`
  const tags = (read('tags') ?? '[]')
    .replace(/^\[|\]$/g, '')
    .split(',')
    .map((t) => t.trim().replace(/^"|"$/g, ''))
    .filter(Boolean)
  const parent = read('parent_id') ?? ''
  return {
    id,
    content: body,
    score: Number(read('score') ?? 1) || 1,
    tags,
    parent_id: parent || null,
    created_at: now,
    updated_at: Number(read('updated_at') ?? now) || now,
    source: 'obsidian',
  }
}

declare module '@deepseek-ai/cordis' {
  interface Context {
    ecoMemory: MemoryTreeService
  }
}

export function apply(ctx: Context, config: ConfigType) {
  const service = new MemoryTreeService(
    config.storeFile,
    config.obsidianVault,
    config.embeddingEndpoint,
    config.embeddingApiKey,
    config.embeddingModel,
    config.vectorWeight,
  )
  ctx.provide('ecoMemory', service)
  if (config.syncOnStart && config.obsidianVault) service.sync('from')
  if (service.vectorEnabled) service.ensureEmbeddings().catch(() => { /* best-effort */ })

  ctx.tools.register(defineTool({
    name: 'eco_memory_add',
    description: 'Add a scored node to the memory tree.',
    parameters: {
      content: { type: 'string', description: 'Memory content' },
      score: { type: 'number', description: 'Importance score, default 1' },
      tags: { type: 'array', items: { type: 'string' }, description: 'Tags' },
      parent_id: { type: 'string', description: 'Optional parent node id' },
    },
    output: {
      schema: { type: 'json' },
      render: (_args, value) => [{ type: 'text', text: JSON.stringify(value, null, 2) }],
    },
    async execute(args) {
      if (!args?.content?.trim()) return { ok: false, error: 'content is required' }
      const node = service.add(args.content.trim(), args.score ?? 1, args.tags ?? [], args.parent_id ?? null)
      return JSON.parse(JSON.stringify({ ok: true, node }))
    },
  }))

  ctx.tools.register(defineTool({
    name: 'eco_memory_search',
    description: 'Search memory nodes by relevance. Hybrid: BM25 + Chinese substring fallback fused with vector cosine similarity when the vector channel is enabled; pure BM25 otherwise.',
    parameters: {
      query: { type: 'string', description: 'Search query' },
      limit: { type: 'number', description: 'Max results, default 10' },
    },
    output: {
      schema: { type: 'json' },
      render: (_args, value) => [{ type: 'text', text: JSON.stringify(value, null, 2) }],
    },
    async execute(args) {
      return JSON.parse(JSON.stringify(await service.search(args?.query ?? '', args?.limit ?? 10)))
    },
  }))

  ctx.tools.register(defineTool({
    name: 'eco_memory_vector_search',
    description: 'Vector-only semantic search (cosine similarity). Returns empty result with vector_enabled=false when no embedding channel is configured.',
    parameters: {
      query: { type: 'string', description: 'Search query' },
      limit: { type: 'number', description: 'Max results, default 10' },
    },
    output: {
      schema: { type: 'json' },
      render: (_args, value) => [{ type: 'text', text: JSON.stringify(value, null, 2) }],
    },
    async execute(args) {
      if (!service.vectorEnabled) {
        return { ok: true, vector_enabled: false, results: [], hint: 'configure embeddingEndpoint or inject an embedding fn to enable vector search' }
      }
      const results = await service.searchVector(args?.query ?? '', args?.limit ?? 10)
      return JSON.parse(JSON.stringify({ ok: true, vector_enabled: true, results }))
    },
  }))

  ctx.tools.register(defineTool({
    name: 'eco_memory_update',
    description: 'Update a memory node (content / score / tags / parent).',
    parameters: {
      id: { type: 'string', description: 'Node id' },
      content: { type: 'string' },
      score: { type: 'number' },
      tags: { type: 'array', items: { type: 'string' } },
      parent_id: { type: 'string', description: 'Set to empty string to detach' },
    },
    output: {
      schema: { type: 'json' },
      render: (_args, value) => [{ type: 'text', text: JSON.stringify(value, null, 2) }],
    },
    async execute(args) {
      const node = service.update(args?.id, {
        content: args?.content,
        score: args?.score,
        tags: args?.tags,
        parent_id: args?.parent_id === '' ? null : args?.parent_id,
      })
      return JSON.parse(JSON.stringify(node ? { ok: true, node } : { ok: false, error: 'node not found' }))
    },
  }))

  ctx.tools.register(defineTool({
    name: 'eco_memory_delete',
    description: 'Delete a memory node by id.',
    parameters: {
      id: { type: 'string', description: 'Node id' },
    },
    output: {
      schema: { type: 'json' },
      render: (_args, value) => [{ type: 'text', text: JSON.stringify(value, null, 2) }],
    },
    async execute(args) {
      return JSON.parse(JSON.stringify({ ok: service.remove(args?.id) }))
    },
  }))

  ctx.tools.register(defineTool({
    name: 'eco_memory_stats',
    description: 'Memory tree statistics: node count, avg score, tags, vector channel status, vault config.',
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
    name: 'eco_memory_sync',
    description: 'Bidirectional sync with the Obsidian vault (to / from / both).',
    parameters: {
      direction: { type: 'string', enum: ['to', 'from', 'both'], description: 'Sync direction, default both' },
    },
    output: {
      schema: { type: 'json' },
      render: (_args, value) => [{ type: 'text', text: JSON.stringify(value, null, 2) }],
    },
    async execute(args) {
      return JSON.parse(JSON.stringify(service.sync((args?.direction ?? 'both') as 'to' | 'from' | 'both')))
    },
  }))

  ctx.tools.register(defineTool({
    name: 'eco_memory_prune',
    description: 'Forgetting & maintenance: drop low-score nodes and nodes untouched for maxAgeDays. Security-tagged nodes (security/denied) are always protected. Children of removed nodes are promoted to roots. Use dryRun=true to preview.',
    parameters: {
      min_score: { type: 'number', description: 'Drop nodes with score strictly below this threshold (default 0 = disabled)' },
      max_age_days: { type: 'number', description: 'Drop nodes not accessed within this many days (default 0 = disabled)' },
      dry_run: { type: 'boolean', description: 'Preview only; no deletion. Default false' },
    },
    output: {
      schema: { type: 'json' },
      render: (_args, value) => [{ type: 'text', text: JSON.stringify(value, null, 2) }],
    },
    async execute(args) {
      return JSON.parse(JSON.stringify(service.prune({
        minScore: args?.min_score,
        maxAgeDays: args?.max_age_days,
        dryRun: args?.dry_run,
      })))
    },
  }))
}

type ConfigType = {
  storeFile: string
  obsidianVault: string
  syncOnStart: boolean
  embeddingEndpoint: string
  embeddingApiKey: string
  embeddingModel: string
  vectorWeight: number
}
