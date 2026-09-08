// 展开明细。核心纪律：无内容不展开 —— 空面板比不展开更糟。
import { strict as A } from 'node:assert'
import { resolveToolDetail } from '../toolViews.ts'
let n = 0; const t = (d, f) => { f(); n++ }

// ── 不可展开的三种情况（都必须返回 null，不出箭头）
t('未实现 detail 的视图不可展开', () => {
  // read-file 对标 WorkBuddy 的 header-only view
  A.equal(resolveToolDetail('read_file', { path: 'a.txt' }, '{"ok":true}'), null)
})
t('结果非 JSON 时仍可展开命令，但不编造输出', () => {
  // 命令在参数里，结果被截断不该让人看不到执行了什么
  const d = resolveToolDetail('shell_run', { command: 'ls' }, '输出被截断…')
  A.equal(d.command, 'ls')
  A.equal(d.output, undefined, '不得编造输出')
})
t('无命令且无结果才真正不可展开', () => {
  A.equal(resolveToolDetail('shell_run', {}, '不是 JSON'), null)
})
t('有工具但无内容时不展开', () => {
  A.equal(resolveToolDetail('grep', { pattern: 'x' }, '{"ok":true,"matches":[]}'), null)
})

// ── shell_run：真实字段 stdout/stderr
t('命令与输出分离', () => {
  const d = resolveToolDetail('shell_run', { command: 'echo hi' },
    '{"ok":true,"exit":0,"stdout":"hi\\n","stderr":""}')
  A.equal(d.kind, 'command')
  A.equal(d.command, 'echo hi')
  A.equal(d.output.trim(), 'hi')
})
t('stderr 也并入输出', () => {
  const d = resolveToolDetail('shell_run', { command: 'x' },
    '{"stdout":"a","stderr":"b"}')
  A.ok(d.output.includes('a') && d.output.includes('b'))
})

// ── grep：真实字段 matches
t('匹配转列表并带文件位置', () => {
  const d = resolveToolDetail('grep', { pattern: 'def' },
    JSON.stringify({ matches: [{ file: 'a.py', lineno: 3, line: 'def run():' }] }))
  A.equal(d.kind, 'list')
  A.equal(d.items[0].text, 'def run():')
  A.equal(d.items[0].sub, 'a.py:3')
})
t('超过 20 条截断并报剩余', () => {
  const ms = Array.from({ length: 26 }, (_, i) => ({ file: 'f', lineno: i, line: `L${i}` }))
  const d = resolveToolDetail('grep', {}, JSON.stringify({ matches: ms }))
  A.equal(d.items.length, 20)
  A.equal(d.more, 6)
})

// ── inspect：真实字段 tools/services/plugins/slots
t('自检转键值对', () => {
  const d = resolveToolDetail('inspect', {},
    JSON.stringify({ tools: [1, 2, 3], services: [1], plugins: [], slots: [1, 1] }))
  A.equal(d.kind, 'kv')
  A.deepEqual(d.rows.find(r => r.k === 'tools'), { k: 'tools', v: '3' })
})

// ── 搜索类
t('搜索结果转列表', () => {
  const d = resolveToolDetail('web_search', { query: 'q' },
    JSON.stringify({ results: [{ title: 'T', url: 'https://x' }] }))
  A.equal(d.items[0].text, 'T')
  A.equal(d.items[0].sub, 'https://x')
})

// ── 健壮性：detail 抛错不得带走对话
t('畸形结果不抛出', () => {
  A.doesNotThrow(() => resolveToolDetail('grep', {}, '{"matches":[null,3,"x"]}'))
  A.doesNotThrow(() => resolveToolDetail('inspect', {}, '{"tools":"not-array"}'))
})

console.log(`✓ toolDetail ${n} 项通过`)
