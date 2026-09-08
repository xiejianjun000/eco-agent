// 工具视图注册表测试。核心是「可分辨」——不同工具必须给出不同的动词。
import { strict as A } from 'node:assert'
import { resolveToolHead, matchPriority, MatchPriority } from '../toolViews.ts'

let n = 0
const t = (d, f) => { f(); n++ }

// ── 优先级语义（对齐 WorkBuddy NONE/DEFAULT/EXACT）
t('字符串精确匹配', () => {
  A.equal(matchPriority('inspect', 'inspect'), MatchPriority.EXACT)
  A.equal(matchPriority('inspect', 'other'), MatchPriority.NONE)
})
t('数组匹配', () => {
  A.equal(matchPriority(['a', 'b'], 'b'), MatchPriority.EXACT)
  A.equal(matchPriority(['a', 'b'], 'c'), MatchPriority.NONE)
})
t('函数可返回 DEFAULT 做族兜底', () => {
  const m = (n) => (n.startsWith('x_') ? MatchPriority.DEFAULT : MatchPriority.NONE)
  A.equal(matchPriority(m, 'x_1'), MatchPriority.DEFAULT)
})

// ── 这是本次改造的核心诉求：工具不能长得一样
t('不同工具给出不同动词', () => {
  const verbs = new Set([
    resolveToolHead('web_search', { query: 'q' }).statusText,
    resolveToolHead('read_file', { path: '/a/b.txt' }).statusText,
    resolveToolHead('shell_run', { command: 'ls' }).statusText,
    resolveToolHead('execute_code', {}).statusText,
    resolveToolHead('inspect', {}).statusText,
    resolveToolHead('api_probe', { url: '/x' }).statusText,
  ])
  A.equal(verbs.size, 6, `动词重复了: ${[...verbs].join(' / ')}`)
})

t('执行中与完成态动词不同', () => {
  const r = resolveToolHead('web_search', { query: 'q' }, 'running')
  const d = resolveToolHead('web_search', { query: 'q' }, 'success')
  A.notEqual(r.statusText, d.statusText)
  A.ok(r.statusText.includes('中'), '执行中应有进行时语感')
})

// ── 三段式内容
t('对象取自参数', () => {
  A.equal(resolveToolHead('web_search', { query: '娄底空气' }).primaryContent, '娄底空气')
})
t('路径只留末段，避免挤掉动词', () => {
  A.equal(resolveToolHead('read_file', { path: '/very/long/dir/a.txt' }).primaryContent, 'a.txt')
})
t('计数进 secondaryInfo', () => {
  A.equal(resolveToolHead('web_search', { query: 'q' }, 'success', 12).secondaryInfo, '12 条')
})
t('无对象时不编造', () => {
  A.equal(resolveToolHead('execute_code', {}).primaryContent, undefined)
})

// ── MCP：整族兜底但不挡精确注册
t('MCP 走族匹配', () => {
  const h = resolveToolHead('mcp__eco-hunan-env__air_quality_hourly', {})
  A.equal(h.viewId, 'mcp-call')
})
t('MCP 动词按内层名细分', () => {
  const q = resolveToolHead('mcp__x__search_foo', {}).statusText
  const g = resolveToolHead('mcp__x__get_bar', {}).statusText
  A.notEqual(q, g)
})
t('MCP 不外露服务器名与原始工具名', () => {
  const h = resolveToolHead('mcp__eco-hunan-env__air_quality_hourly', {})
  const all = `${h.statusText}${h.primaryContent || ''}${h.secondaryInfo || ''}`
  A.ok(!all.includes('mcp__'), '泄漏了原始工具名')
  A.ok(!all.includes('eco-hunan-env'), '泄漏了服务器名')
})

// ── 兜底：对齐 unknown-tool，不白屏不吐 JSON
t('未知工具走 fallback 但结构完整', () => {
  const h = resolveToolHead('never_seen_tool', {})
  A.equal(h.viewId, 'fallback')
  A.ok(h.statusText, 'fallback 也必须有动词')
  A.ok(h.icon, 'fallback 也必须有图标')
})

// ── 高频工具必须已覆盖（viewId 不得为 fallback）
t('eco 高频工具全部有专属视图', () => {
  const must = ['web_search', 'read_file', 'write_file', 'shell_run', 'execute_code',
                'grep', 'glob', 'inspect', 'api_probe', 'audit_tail',
                'kb_search', 'statute_lookup']
  const missed = must.filter((x) => resolveToolHead(x, {}).viewId === 'fallback')
  A.deepEqual(missed, [], `这些工具还没有专属视图: ${missed.join(', ')}`)
})

console.log(`✓ toolViews ${n} 项通过`)

// ── 创建 vs 编辑：WorkBuddy 实录里这是两种不同的行
//    「创建 connector-meta.json +24 -0」 vs 「编辑 db.py +1 -1」
t('创建与编辑动词不同', () => {
  const create = resolveToolHead('write_file', { path: 'a.json' }, 'success')
  const edit = resolveToolHead('edit_file', { path: 'b.py', old_string: 'x' }, 'success')
  A.notEqual(create.statusText, edit.statusText)
  A.equal(create.statusText, '创建')
  A.equal(edit.statusText, '编辑')
})
t('行数走独立字段而非文字', () => {
  const h = resolveToolHead('write_file', { path: 'a.json' }, 'success', undefined,
                            { added: 24, removed: 0 })
  A.equal(h.added, 24)
  A.equal(h.removed, 0)
  A.ok(!h.statusText.includes('24'), '行数不应混进动词')
  A.ok(!(h.primaryContent || '').includes('24'), '行数不应混进文件名')
})
t('pending 态有独立文案', () => {
  A.equal(resolveToolHead('never_seen', {}, 'pending').statusText, '待执行')
})
t('失败态不改变结构', () => {
  const h = resolveToolHead('write_file', { path: 'a.py' }, 'error')
  A.ok(h.statusText, '失败也要有动词')
  A.equal(h.primaryContent, 'a.py', '失败仍应显示对象')
})

console.log(`✓ toolViews 追加项通过`)
