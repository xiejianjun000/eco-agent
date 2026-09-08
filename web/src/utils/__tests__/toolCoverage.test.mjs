// 覆盖率守卫：每个内置工具都必须有专属视图，不得掉回 fallback。
// 实测起点：108 个工具里 106 个走 fallback，界面上全显示「已执行」——
// 查空气质量、算碳排、办许可证、出图长得一模一样，这正是「工具混在一起」。
import { strict as A } from 'node:assert'
import { readFileSync } from 'node:fs'
import { resolveToolHead } from '../toolViews.ts'

const REG = new URL('../../../../agent_core/tools_registry.py', import.meta.url).pathname
const src = readFileSync(REG, 'utf8')
const names = [...new Set([...src.matchAll(/"name": "([a-z_0-9]+)"/g)].map(m => m[1]))]

A.ok(names.length > 90, `只解析到 ${names.length} 个工具，正则可能失效`)

const miss = names.filter(n => resolveToolHead(n, {}).viewId === 'fallback')
A.deepEqual(miss, [], `${miss.length} 个工具没有专属视图: ${miss.slice(0, 12).join(', ')}`)

// 光有视图不够，动词必须真的能区分
const verbs = new Map()
for (const n of names) {
  const v = resolveToolHead(n, {}).statusText
  verbs.set(v, (verbs.get(v) || 0) + 1)
}
const worst = [...verbs.entries()].sort((a, b) => b[1] - a[1])[0]
A.ok(worst[1] <= names.length * 0.45,
  `动词「${worst[0]}」覆盖了 ${worst[1]}/${names.length} 个工具，区分度不足`)

// 任何工具都不得把原始名漏进头部
for (const n of names) {
  const h = resolveToolHead(n, {})
  const all = `${h.statusText}${h.primaryContent || ''}`
  A.ok(!all.includes('_'), `${n} 的头部疑似漏出原始工具名: ${all}`)
}

console.log(`✓ 工具覆盖率 ${names.length}/${names.length}，动词族 ${verbs.size} 种`)
