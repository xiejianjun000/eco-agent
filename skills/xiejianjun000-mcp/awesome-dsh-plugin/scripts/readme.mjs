/**
 * Shared README parsing + ordering primitives used by build-site.mjs and
 * check-order.mjs.
 *
 * Plugins are sorted by repo identifier (owner/repo) inside each category so
 * the list stays neutral — no stars bias, no insertion-order luck. Sorting
 * keys come from the URL (identical across locales), never from the line text
 * (the en README drops the owner prefix on some entries).
 */
import fs from 'node:fs'

export const CAT_IDS = ['ui', 'theme', 'session', 'memory', 'tools', 'skill', 'workflow', 'notify', 'model', 'dev', 'fun']

// repo identifier for alphabetical ordering; monorepo /tree/ paths fold into
// their owner/repo, with the full path as the deterministic tie-break.
export const sortKey = (url) => url.replace(/^https:\/\/github\.com\//, '').replace(/\/tree\/.*$/, '').toLowerCase()

export const cmpByKey = (aUrl, bUrl) =>
  sortKey(aUrl).localeCompare(sortKey(bUrl), 'en') || aUrl.toLowerCase().localeCompare(bUrl.toLowerCase(), 'en')

// url -> {name, url, desc, cat, line} for every parseable plugin line.
export function parseReadme(readmePath, categories) {
  const text = fs.readFileSync(readmePath, 'utf8')
  const out = new Map()
  let cat = null
  const lines = text.split('\n')
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    const h = line.match(/^#{2,3} (.+)$/)
    if (h) {
      cat = CAT_IDS.find((id) => h[1].includes(categories[id])) ?? null
      continue
    }
    const m = line.match(/^- \[(.+?)\]\((https:\/\/github\.com\/[^)]+)\) [—-] (.+)$/)
    if (m && cat) out.set(m[2], { name: m[1], url: m[2], desc: m[3], cat, line: i + 1 })
  }
  return out
}
