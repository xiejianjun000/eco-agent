#!/usr/bin/env node
/**
 * Lint: every plugin line in each locale README must be sorted by owner/repo
 * inside its category. Offline, zero side effects — safe for PR checks.
 *
 * Usage: node scripts/check-order.mjs
 * To normalize: run node scripts/build-site.mjs
 */
import LOCALES from '../site/locales.mjs'
import { CAT_IDS, cmpByKey, parseReadme } from './readme.mjs'

let bad = 0
for (const loc of LOCALES) {
  const entries = [...parseReadme(loc.readme, loc.categories).values()]
  for (const id of CAT_IDS) {
    const group = entries.filter((e) => e.cat === id)
    const sorted = [...group].sort((a, b) => cmpByKey(a.url, b.url))
    for (let i = 0; i < group.length; i++) {
      if (group[i].url !== sorted[i].url) {
        bad++
        if (bad <= 20) console.log(`${loc.readme}:${group[i].line} out of order → expected ${sorted[i].url}`)
      }
    }
  }
}
if (bad) {
  console.log(`\n${bad} entries out of alphabetical order (by owner/repo). Run \`node scripts/build-site.mjs\` to normalize.`)
  process.exit(1)
}
console.log('order OK: plugin lines sorted by owner/repo in every category and locale')
