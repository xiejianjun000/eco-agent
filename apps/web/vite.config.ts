import { existsSync, readFileSync } from 'node:fs'
import { readFile, writeFile } from 'node:fs/promises'
import { dirname, extname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { globSync } from 'node:fs'
import { defineConfig } from 'vite'
import type { Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import { clientBuildEnvironmentDefines } from '../../scripts/client-build-environment.ts'
import { productWebBundleIsolation } from './product-isolation.ts'

const src = (rel: string): string => fileURLToPath(new URL(rel, import.meta.url))
const STANDALONE_ERROR = 'apps/web is not a standalone application: bare Vite cannot inject window.__DSH_BOOT__. '
  + 'From a repository checkout, run `pnpm dsh web`; an installed package uses `dsh web`. '
  + 'For client-plugin HMR, run `pnpm run dev:web`, which starts `dsh web` and the rebuild watchers together.'
const DEFAULT_CLIENT_TITLE = 'DSH Local Build'

/** Escape build-time text before placing it in the HTML title element. */
function escapeHtmlText(value: string): string {
  return value.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

/** Project the public build title into the initial HTML document. */
function clientDocumentTitle(): Plugin {
  const title = escapeHtmlText(process.env.DSH_CLIENT_TITLE ?? DEFAULT_CLIENT_TITLE)
  return {
    name: 'dsh-client-document-title',
    transformIndexHtml(html) {
      return html.replace('<title>DSH Local Build</title>', `<title>${title}</title>`)
    },
  }
}

/** Keep the redistribution license beside the bundled brand font. */
function brandFontLicense(): Plugin {
  return {
    name: 'dsh-brand-font-license',
    async generateBundle() {
      this.emitFile({
        type: 'asset',
        fileName: 'assets/fonts/Montserrat-OFL.txt',
        source: await readFile(src('../../packages/client/ui-theme/src/styles/Montserrat-OFL.txt')),
      })
    },
  }
}

/** Fail before a Vite dev or preview server can expose the boot-manifest-free shell. */
function rejectStandaloneServe(): Plugin {
  return {
    name: 'dsh-reject-standalone-web-serve',
    config(_config, env) {
      if (env.command === 'serve') throw new Error(STANDALONE_ERROR)
    },
  }
}

/**
 * Emit preview.html beside index.html: the built index page with one module
 * script — the worker bootstrap entry — spliced ahead of its entry tag. Both
 * pages share every chunk; the extra tag is the only difference, so the
 * static worker deployment ships the served page verbatim plus its
 * bootstrap.
 */
function emitPreviewPage(): Plugin {
  let bootstrapFile: string | undefined
  let write = true
  let written = false
  let outputDirectory = ''
  return {
    name: 'dsh-emit-preview-page',
    configResolved(config) {
      write = config.build.write
      outputDirectory = resolve(config.root, config.build.outDir)
    },
    buildStart() {
      bootstrapFile = undefined
      written = false
    },
    generateBundle(_options, bundle) {
      if (!write) return
      for (const item of Object.values(bundle)) {
        if (item.type === 'chunk' && item.isEntry && item.name === 'bootstrap') bootstrapFile = item.fileName
      }
      if (bootstrapFile === undefined) throw new Error('vite: preview bootstrap entry missing from the bundle')
    },
    writeBundle() { written = true },
    async closeBundle() {
      if (!write || !written || bootstrapFile === undefined) return
      const page = await readFile(resolve(outputDirectory, 'index.html'), 'utf8')
      const anchor = page.indexOf('<script type="module"')
      if (anchor === -1) throw new Error('vite: built index.html lost its module entry tag')
      const tag = `<script type="module" crossorigin src="./${bootstrapFile}"></script>`
      await writeFile(resolve(outputDirectory, 'preview.html'), `${page.slice(0, anchor)}${tag}${page.slice(anchor)}`)
    },
  }
}

/**
 * Vendor-chunk membership, by exact npm package name — the heavy render
 * families (math, highlight, markdown) that change only on dependency bumps.
 * Only packages workspace code imports DIRECTLY need listing: their private
 * transitive dependencies (oniguruma machinery, character tables, …) are
 * imported solely by these and rollup's chunk coloring pulls them into
 * vendor automatically. A dependency shared with index-side code falls back
 * to index — a few kB of dilution, never a correctness problem. Anything not
 * listed (react family, the vendored cordis workspace, tiny helpers like
 * anser/clsx, all workspace code) stays in the default `index` chunk, so
 * editing shell code re-hashes only index and returning clients keep the
 * cached vendor chunk.
 *
 * Every member must be React-free. A package that
 * imports react/jsx-runtime must never be listed — rollup folds a module
 * shared between the entry and a manual chunk into the manual chunk, so one
 * react-importing member would drag the single shared react copy into
 * vendor. The React side of markdown/math rendering is workspace code and
 * rides index.
 */
const VENDOR_PACKAGES: ReadonlySet<string> = new Set([
  // math
  'katex',
  // syntax highlight (@shikijs/langs is handled separately below —
  // lazy grammars must not land here)
  'shiki',
  // markdown parse pipeline (micromark/mdast; the incremental React renderer
  // over it is workspace code)
  'mdast-util-from-markdown',
  'mdast-util-gfm',
  'mdast-util-math',
  'micromark-core-commonmark',
  'micromark-extension-gfm',
  'micromark-extension-math',
  'micromark-factory-space',
  'micromark-util-character',
  'micromark-util-classify-character',
  'micromark-util-sanitize-uri',
  'micromark-util-symbol',
  'micromark-util-types',
])

/**
 * Boot grammars statically imported by ui-primitives' highlight.ts
 * (`@shikijs/langs/typescript` → `dist/typescript.mjs`, etc.). They live in
 * the same package as the lazy read-card grammars, but unlike those they are
 * part of the initial load and belong in the vendor chunk; the lazy ones must
 * stay unassigned so each keeps its own on-demand chunk.
 */
const BOOT_GRAMMAR_FILES: readonly string[] = [
  'dist/typescript.mjs',
  'dist/shellscript.mjs',
  'dist/json.mjs',
]

/** Font asset extensions routed to assets/fonts/ (KaTeX's woff2/woff/ttf faces). */
const FONT_EXTENSIONS: readonly string[] = ['.woff2', '.woff', '.ttf']

/**
 * npm package name of a resolved module id: the segment after the last
 * `node_modules/`. pnpm nests the real package under an inner node_modules.
 */
function npmPackageOf(id: string): string | undefined {
  const parts = id.split('/node_modules/')
  if (parts.length === 1) return undefined
  const [first, second] = parts[parts.length - 1].split('/')
  if (first.startsWith('.')) return undefined // .pnpm store segment, not a package
  if (first.startsWith('@')) return second === undefined ? undefined : `${first}/${second}`
  return first
}

/**
 * Local-preview bridge: resolve every in-repo `@eco-agent/*` workspace package
 * straight to its TypeScript `src` so Vite/esbuild compiles it on the fly. This
 * lets `vite build` succeed without first running the full monorepo `lib` build
 * (tsc -b + tsdown), which the upstream 0.2.0-rc.2 developer preview has not
 * fully wired for every dsh.bundle package. The bridge is local-only and is
 * reverted before any production build / publish.
 *
 * `replacement` is a function (not a static string) so each import is resolved
 * against the package's own `exports` map: a built target like
 * `./lib/styles/brand-font.css` is mapped back to `./src/styles/brand-font.css`,
 * while JS subpaths like `./client` map to `./src/client`. Resolution only
 * succeeds when the source file actually exists; otherwise we return undefined
 * and Vite falls back to the package's normal (built) resolution.
 */
type WorkspaceEntry = { pkgDir: string; exports: Record<string, unknown> }
const workspaceSourceRegistry: Map<string, WorkspaceEntry> = (() => {
  const reg = new Map<string, WorkspaceEntry>()
  const selfDir = src('.')
  const roots = ['packages', 'apps', 'vendor', 'native/system', 'benchmarks', 'website']
  for (const root of roots) {
    const base = src(`../../${root}`)
    const patterns = [join(base, '*', 'package.json'), join(base, '*', '*', 'package.json')]
    for (const pattern of patterns) {
      for (const pkgPath of globSync(pattern)) {
        let pkg: { name?: string; exports?: Record<string, unknown> } = {}
        try { pkg = JSON.parse(readFileSync(pkgPath, 'utf8')) } catch { continue }
        const name = pkg.name
        if (!name || !name.startsWith('@eco-agent/')) continue
        const pkgDir = dirname(pkgPath)
        if (pkgDir === selfDir) continue
        if (!existsSync(join(pkgDir, 'src'))) continue
        reg.set(name, { pkgDir, exports: pkg.exports ?? {} })
      }
    }
  }
  return reg
})()

/** Probe a source path, tolerating the .js→.ts extension gap between a
 * package's built `exports` target and its TypeScript source. */
function probeSource(pkgDir: string, rel: string): string | undefined {
  const abs = join(pkgDir, rel)
  if (existsSync(abs)) return abs
  const ext = extname(rel)
  const stem = ext ? rel.slice(0, rel.length - ext.length) : rel
  for (const e of ['.ts', '.tsx', '.jsx', '.mjs', '.js']) {
    const variant = join(pkgDir, stem + e)
    if (existsSync(variant)) return variant
  }
  for (const e of ['.ts', '.tsx', '.js']) {
    const idx = join(pkgDir, rel, `index${e}`)
    if (existsSync(idx)) return idx
  }
  return undefined
}

function resolveWorkspaceSource(name: string, subpath: string): string | undefined {
  const entry = workspaceSourceRegistry.get(name)
  if (!entry) return undefined
  // main entry: prefer an explicit index module, else the src directory
  if (subpath === '') {
    return probeSource(entry.pkgDir, 'src/index')
      ?? (existsSync(join(entry.pkgDir, 'src')) ? join(entry.pkgDir, 'src') : undefined)
  }
  // direct src/<subpath> (covers the `./src/*` wildcard exports)
  const direct = probeSource(entry.pkgDir, `src/${subpath}`)
  if (direct) return direct
  // via exports map: built target → source tree
  const key = `./${subpath}`
  const exp = entry.exports[key]
  if (exp) {
    const target = typeof exp === 'string' ? exp : ((exp as any).default ?? (exp as any).types)
    if (typeof target === 'string') {
      let rel = target.replace(/^\.\//, '')
      rel = rel.replace(/^lib\/types\//, 'src/').replace(/^lib\//, 'src/')
      const mapped = probeSource(entry.pkgDir, rel)
      if (mapped) return mapped
    }
  }
  // common source asset directories for asset subpaths that don't mirror 1:1
  for (const dir of ['styles', 'assets', 'public', 'fonts']) {
    const guess = probeSource(entry.pkgDir, `src/${dir}/${subpath}`)
    if (guess) return guess
  }
  return undefined
}

function workspaceSourceAliases(): Array<{ find: RegExp; replacement: (id: string) => string | undefined }> {
  const aliases: Array<{ find: RegExp; replacement: (id: string) => string | undefined }> = []
  for (const name of workspaceSourceRegistry.keys()) {
    const safe = name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    aliases.push({
      find: new RegExp(`^${safe}(/.*)?$`),
      replacement: (id: string) => {
        // Preserve Vite query/hash (e.g. `?worker`) so loaders downstream still
        // see them after we point the specifier at the package's source tree.
        const cut = id.search(/[?#]/)
        const query = cut >= 0 ? id.slice(cut) : ''
        const baseId = cut >= 0 ? id.slice(0, cut) : id
        const subpath = baseId.slice(name.length).replace(/^\//, '')
        const resolved = resolveWorkspaceSource(name, subpath)
        if (!resolved) return undefined
        return resolved + query
      },
    })
  }
  return aliases
}

export default defineConfig({
  // Relative asset URLs: preview.html mounts the same output under any base
  // directory, and the served index resolves identically from the site root.
  base: './',
  plugins: [
    rejectStandaloneServe(), clientDocumentTitle(), brandFontLicense(), react(), emitPreviewPage(),
    productWebBundleIsolation(src('../..'), src('.')),
  ],
  build: {
    // The worker bootstrap holds its page at top-level await; Vite's default
    // `modules` target (es2020-era) rejects that syntax.
    target: 'es2022',
    sourcemap: true,
    rollupOptions: {
      input: {
        index: src('./index.html'),
        // Standalone entry, not an index.html script tag: Vite folds every
        // module tag of one page into a single synthetic entry, and only a
        // separate input keeps the shared page chunks bootstrap-free.
        bootstrap: src('./src/preview.ts'),
      },
      output: {
        // The worker-preview surface groups under dist/preview/ (the page
        // itself stays at dist/preview.html), so the published payload can
        // exclude it as one directory.
        entryFileNames(chunk): string {
          return chunk.name === 'bootstrap' ? 'preview/[name]-[hash].js' : 'assets/[name]-[hash].js'
        },
        // Output layout: the two main chunks stay at assets/ root; lazy
        // @shikijs/langs grammar chunks group under assets/langs/; fonts
        // (all KaTeX faces referenced by vendor.css) group under
        // assets/fonts/. Sourcemaps need no arrangement: rollup writes each
        // .map next to its js and references it by bare relative filename.
        chunkFileNames(chunk): string {
          // Grammar chunks are recognized by their member modules, not the
          // facade: shared embedded-grammar chunks (e.g. html+javascript,
          // split out because php/ruby/mdx embed them) have no facade at all.
          // index and vendor are excluded by name — vendor legitimately
          // carries the three boot grammars.
          if (chunk.name === 'index' || chunk.name === 'vendor') return 'assets/[name]-[hash].js'
          const isLangChunk = chunk.moduleIds.some(id => id.includes('/node_modules/@shikijs/langs/'))
          return isLangChunk ? 'assets/langs/[name]-[hash].js' : 'assets/[name]-[hash].js'
        },
        assetFileNames(asset): string {
          const fileName = asset.names[0] ?? ''
          const isFont = FONT_EXTENSIONS.some(ext => fileName.endsWith(ext))
          return isFont ? 'assets/fonts/[name]-[hash][extname]' : 'assets/[name]-[hash][extname]'
        },
        manualChunks(id: string): string | undefined {
          const pkg = npmPackageOf(id)
          if (pkg === undefined) return undefined // workspace + vendored cordis: index
          if (pkg === '@shikijs/langs') {
            return BOOT_GRAMMAR_FILES.some(file => id.endsWith(`/${file}`)) ? 'vendor' : undefined
          }
          return VENDOR_PACKAGES.has(pkg) ? 'vendor' : undefined
        },
      },
    },
  },
  worker: {
    // The preview worker rides dist/preview/ with the rest of that surface.
    rollupOptions: { output: { entryFileNames: 'preview/[name]-[hash].js' } },
  },
  resolve: {
    // One instance per shared npm identity: a bare specifier otherwise resolves
    // from the importer's directory, so a diverging range ships a second React
    // and splits hook and element identity. Entries are package ids — they cover
    // react/jsx-runtime and react-dom/client — and resolve from this package's
    // node_modules, so react must stay a devDependency here and any watcher must
    // run vite from this directory (scripts/dev-web.ts). Workspace packages need
    // no entry: pnpm links each of them to a single directory.
    dedupe: ['react', 'react-dom'],
    // Workspace packages are consumed as built lib products: each resolves
    // through its own package.json exports from the importer's directory, and
    // CSS still rides Vite's pipeline because the client build preset emits it
    // beside the bundle. Plugin packages never enter this graph; they arrive as
    // runtime bundles through the client module system. The remaining alias
    // browserizes the vendored Cordis Loader's only Node import.
    alias: [
      { find: /^node:module$/, replacement: src('./src/node-module-stub.ts') },
      ...workspaceSourceAliases(),
    ],
  },
  define: {
    ...clientBuildEnvironmentDefines(process.env),
    // vendored loader internal.ts: fromInternal() probes the Node major —
    // "0.0.0" takes neither branch, returning undefined (exactly the empty
    // internal slot the shell boot fills with the client module loader).
    'process.versions.node': '"0.0.0"',
    'process.execArgv': '[]',
    // vendored loader index.ts: envData falls to its default branch.
    'process.env.CORDIS_SHARED': 'undefined',
  },
})
