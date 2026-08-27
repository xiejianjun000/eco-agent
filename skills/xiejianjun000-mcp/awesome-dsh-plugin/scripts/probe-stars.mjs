#!/usr/bin/env node
/**
 * Probe GitHub repo stats for the listed plugins and cache them, so the
 * site can rank plugins by popularity (the sort control on the web page).
 * Each entry records the star count plus the repo creation date (a proxy for
 * the first-commit time), which powers the "latest" sort modes.
 *
 * For every plugin URL in the default-locale README that is missing from
 * data/stars.json, lacks a field, or was last checked over RECHECK_DAYS ago:
 *   GET https://api.github.com/repos/{owner}/{repo}
 *
 * Revalidation uses If-None-Match (the stored ETag): GitHub answers 304 for
 * unchanged repos without consuming the primary rate limit, so routine runs
 * are cheap. Entries missing a recorded createdAt are backfilled with an
 * unconditional request (a 304 carries no body to read the date from).
 * A GITHUB_TOKEN (5000 req/hr) makes the initial full seed fast; without one
 * the unauthenticated 60 req/hr wall just stops the probe early and leaves
 * the existing cache intact.
 *
 * Results are cached in data/stars.json:
 *   { "<github url>": { stars, createdAt, etag, checkedAt } }.
 * Network failures or rate-limit exhaustion keep the existing entry untouched.
 *
 * Usage: node scripts/probe-stars.mjs
 */
import fs from 'node:fs'
import LOCALES from '../site/locales.mjs'

const CACHE_FILE = 'data/stars.json'
const RECHECK_DAYS = 7
const CONCURRENCY = 6
const TOKEN = process.env.GITHUB_TOKEN || ''

const cache = fs.existsSync(CACHE_FILE) ? JSON.parse(fs.readFileSync(CACHE_FILE, 'utf8')) : {}

const readme = fs.readFileSync(LOCALES[0].readme, 'utf8')
const urls = [...readme.matchAll(/^- \[.+?\]\((https:\/\/github\.com\/[^)]+)\) [—-] /gm)].map((m) => m[1])

const today = new Date().toISOString().slice(0, 10)
const stale = (entry) =>
  entry === undefined
  || entry.createdAt === undefined
  || (Date.now() - new Date(entry.checkedAt).getTime()) / 86400000 > RECHECK_DAYS

const pending = urls.filter((url) => stale(cache[url]))
console.log(`${urls.length} listed, ${pending.length} to (re)probe`)

async function fetchRepo(url) {
  const repoPath = url.replace('https://github.com/', '').replace(/\/$/, '')
  const headers = {
    accept: 'application/vnd.github+json',
    'user-agent': 'awesome-dsh-plugin-stars-probe',
    'x-github-api-version': '2022-11-28',
  }
  if (TOKEN) headers.authorization = `Bearer ${TOKEN}`
  const prev = cache[url]
  // Backfill entries that predate the createdAt field: skip the conditional
  // header so a 200 (with the body we need) is returned instead of a 304.
  if (prev?.etag && prev.createdAt !== undefined) headers['if-none-match'] = prev.etag
  let res
  try {
    res = await fetch(`https://api.github.com/repos/${repoPath}`, {
      headers,
      signal: AbortSignal.timeout(10000),
    })
  } catch {
    return { defer: true }
  }
  if (res.status === 304) return { entry: { stars: prev.stars, createdAt: prev.createdAt, etag: prev.etag, checkedAt: today } }
  if (res.status === 403 && res.headers.get('x-ratelimit-remaining') === '0') return { rate: true }
  if (res.status === 429) return { rate: true }
  if (!res.ok) return { defer: true }
  const body = await res.json().catch(() => null)
  if (!body) return { defer: true }
  const createdAt = typeof body.created_at === 'string' ? body.created_at.slice(0, 10) : null
  return { entry: { stars: body.stargazers_count ?? 0, createdAt, etag: res.headers.get('etag'), checkedAt: today } }
}

let done = 0
let stopped = false
for (let i = 0; i < pending.length && !stopped; i += CONCURRENCY) {
  const batch = pending.slice(i, i + CONCURRENCY)
  const results = await Promise.all(batch.map(async (url) => [url, await fetchRepo(url)]))
  for (const [url, result] of results) {
    if (result.rate) { stopped = true; continue }
    if (result.defer) {
      if (cache[url] === undefined) cache[url] = { stars: null, checkedAt: today }
      continue
    }
    cache[url] = result.entry
  }
  done += batch.length
  console.log(`probed ${Math.min(done, pending.length)}/${pending.length}${stopped ? ' (rate limit — stopping)' : ''}`)
}

const sorted = Object.fromEntries(Object.entries(cache).sort(([a], [b]) => a.localeCompare(b)))
fs.writeFileSync(CACHE_FILE, JSON.stringify(sorted, null, 1) + '\n')
const known = Object.values(sorted).filter((e) => e.stars !== null).length
console.log(`stars cache written: ${known}/${Object.keys(sorted).length} with star counts`)
