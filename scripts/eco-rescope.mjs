/**
 * eco-rescope — white-label rename for the eco-agent fork of deepseek-harness.
 *
 * Renames `@deepseek-ai/<pkg>` → `@eco-agent/<pkg>` for every *internal* package
 * (a package whose name is declared in some repo package.json). External packages
 * published by DeepSeek to npm (e.g. `@deepseek-ai/libreoffice-kit` native
 * prebuilds) are intentionally LEFT as `@deepseek-ai/*` — eco-agent consumes them
 * as third-party deps and does NOT republish them under its own scope.
 *
 * This is the ECO-side counterpart of upstream `scripts/rescope-vendor.ts`, which
 * only renamed the vendored Cordis framework *into* `@deepseek-ai` for DeepSeek's
 * own use and therefore cannot be reused.
 *
 * Matching rules:
 *  - `@deepseek-ai/<name>(/subpath)?` → `@eco-agent/<name>(/subpath)?`  iff the
 *    package name (segment before the first `/`) is in the internal set S.
 *  - `@deepseek-ai/deepseek-harness` (the upstream *repo* path, attribution) is
 *    always preserved.
 *  - External packages (name segment not in S) are never renamed.
 *
 * Excluded (recorded/generated/upstream-verbatim, mirror upstream):
 *   scripts/eco-rescope.mjs, .agents/notes/, scripts/snapshots/, *.i18n.yaml,
 *   pnpm-lock.yaml, docs/rescope.md(.zh), vendor per-package README.md and LICENSE.
 *
 * Usage: `node scripts/eco-rescope.mjs [--dry|--apply|--check]`
 */

import { execFileSync } from 'node:child_process'
import { readFileSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'

const root = resolve(import.meta.dirname, '..')

const EXTENSIONS = ['.ts', '.tsx', '.js', '.mjs', '.cjs', '.tpl', '.json', '.yml', '.yaml', '.md', '.toml', '.txt', '.css', '.html', '.snap', '.spec']

function isExcluded(file) {
  if (file === 'scripts/eco-rescope.mjs') return true
  if (file.startsWith('.agents/notes/')) return true
  if (file.startsWith('scripts/snapshots/')) return true
  if (file.endsWith('.i18n.yaml')) return true
  if (file === 'pnpm-lock.yaml') return true
  if (file === 'docs/rescope.md' || file === 'docs/rescope.zh.md') return true
  if (/^vendor\/[^/]+\/(README\.md|LICENSE)$/.test(file)) return true
  return !EXTENSIONS.some((ext) => file.endsWith(ext))
}

// Build the internal package set S from every repo package.json `name`.
function internalSet() {
  const S = new Set()
  const out = execFileSync('git', ['ls-files', '**/package.json'], { cwd: root, encoding: 'utf8' })
  for (const f of out.split('\n').filter(Boolean)) {
    try {
      const d = JSON.parse(readFileSync(resolve(root, f), 'utf8'))
      const n = d.name
      if (typeof n === 'string' && n.startsWith('@eco-agent/')) S.add(n.slice('@eco-agent/'.length))
    } catch { /* ignore */ }
  }
  return S
}

const RE = /@deepseek-ai\/(?!deepseek-harness\b)([A-Za-z0-9._/-]+)/g

function rewrite(text, S) {
  return text.replace(RE, (full, pkg) => {
    const name = pkg.split('/')[0]
    return S.has(name) ? '@eco-agent/' + pkg : full
  })
}

function main() {
  const args = process.argv.slice(2)
  const mode = args.includes('--apply') ? 'apply' : args.includes('--check') ? 'check' : 'dry'
  const S = internalSet()
  const files = execFileSync('git', ['ls-files', '-z'], { cwd: root, encoding: 'utf8' })
    .split('\0')
    .filter((f) => f !== '' && !isExcluded(f))

  const counts = new Map()
  const residue = [] // internal @deepseek-ai that should have been renamed

  for (const file of files) {
    const path = resolve(root, file)
    let before
    try {
      before = readFileSync(path, 'utf8')
    } catch {
      continue
    }
    if (mode === 'check') {
      let m
      RE.lastIndex = 0
      while ((m = RE.exec(before)) !== null) {
        const name = m[1].split('/')[0]
        if (name !== 'deepseek-harness' && S.has(name)) {
          residue.push(`${file} (${m[1]})`)
        }
      }
      continue
    }
    const after = rewrite(before, S)
    if (after === before) continue
    const kind = file.endsWith('package.json') ? 'package.json'
      : /\.(ts|tsx|js|mjs|cjs|tpl)$/.test(file) ? 'code'
      : /\.(yml|yaml)$/.test(file) ? 'yaml'
      : file.endsWith('.json') ? 'json'
      : 'markdown'
    const cur = counts.get(kind) ?? { files: 0, lines: 0 }
    counts.set(kind, { files: cur.files + 1, lines: cur.lines + Math.abs(after.split('\n').length - before.split('\n').length) })
    if (mode === 'apply') writeFileSync(path, after)
  }

  if (mode === 'check') {
    if (residue.length === 0) {
      console.log('eco-rescope: OK — all internal @deepseek-ai packages renamed; external + repo path preserved.')
    } else {
      console.error(`eco-rescope: ${residue.length} internal @deepseek-ai ref(s) still present:`)
      residue.slice(0, 30).forEach((r) => console.error('  ' + r))
      process.exitCode = 1
    }
    return
  }

  console.log(`eco-rescope: ${mode} over ${files.length} tracked files (internal set S=${S.size})`)
  for (const kind of [...counts.keys()].sort()) {
    const { files: c, lines } = counts.get(kind)
    console.log(`  ${kind.padEnd(12)} ${String(c).padStart(5)} file(s), ${String(lines)} line(s)`)
  }
  if (mode === 'apply') {
    console.log('eco-rescope: applied. Next: `pnpm install` then `node scripts/eco-rescope.mjs --check`.')
  }
}

if (process.argv[1] !== undefined) main()
